"""Phase-1 acceptance tests for ``four_side_1024/fslw/ports_audit.py``.

Covers the new FSLW dual-height real 2x16 MPO port model (``fslw/SPEC.md`` §2/§9):

* both frozen connectivity CSVs load independently of ``fslw/ports.py`` and of
  the previous-round ``four_side_1024/inputs.py``;
* per-plane port use: 512 connections / 1024 real ports per plane, every
  4 sides x 16 connectors x 16 columns port used exactly once;
* row -> plane rule (row 1 -> z1 opposite, row 2 -> z2 adjacent), 0.25 mm column
  pitch, 0.5 mm row separation, `along` formula, inward directions;
* the 2048 real 3D physical port coordinates (64 connectors x 32 fibers);
* negative controls: row/plane mismatch, duplicated port, tampered physical
  coordinates must all be detected;
* comparison against Lead's ``fslw/ports.py``: all 2048 identities must match
  exactly (0.0 mm deviation) and no row->plane inconsistency may be reported;
* full artifact build (JSON + CSV + PNG + README) into a temporary directory.

Run from ``OpticalWaveguideRouter2D``::

    .\\.venv\\Scripts\\python.exe -m pytest four_side_1024\\fslw\\tests_fslw\\test_ports_fslw.py -q
"""
import copy
import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from four_side_1024.fslw import ports_audit as A

CSV_AVAILABLE = A.V1_CSV.exists() and A.V2_CSV.exists()
pytestmark = pytest.mark.skipif(not CSV_AVAILABLE,
                                reason='frozen V1/V2 connectivity CSV not found')

REQUIRED_README_PHRASES = [
    '仿真坐标',
    '未实现任何 z 方向过渡',
    '玻璃厚度与接头安装方向尚未确认',
    '机械干涉',
    '跨平面的 XY 投影重叠不是同层冲突',
    '同层冲突',
]


# ---------------------------------------------------------------------------
# fixtures (derivation is deterministic; derive once per session)
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def state_v1():
    return A.derive_ports(A.V1_CSV)


@pytest.fixture(scope='module')
def state_v2():
    return A.derive_ports(A.V2_CSV)


@pytest.fixture(scope='module')
def comparison():
    return A.compare_with_lead_ports()


# ---------------------------------------------------------------------------
# 1. model constants / derivations
# ---------------------------------------------------------------------------
def test_model_constants_and_formulas():
    # IEC 61754-7-3:2019 2x16 MPO + 150 mm board / 16 connectors per side / 9 mm
    assert (A.BOARD_MM, A.CONNECTORS_PER_SIDE, A.COLUMNS, A.ROWS) == (150.0, 16, 16, 2)
    assert A.CHANNELS_PER_CONNECTOR == 32
    assert A.FIBER_COLUMN_PITCH_MM == 0.25
    assert A.FIBER_ROW_PITCH_MM == 0.50
    assert A.CONNECTOR_PITCH_MM == 9.0
    assert A.FIRST_CONNECTOR_CENTER_MM == 7.5  # (150 - 15*9)/2
    assert A.PLANE_Z_MM == {1: 0.0, 2: 0.5}
    assert A.PLANE_ROW == {'z1': 1, 'z2': 2}
    # along = connector_center + (column - 8.5) * 0.25
    assert A.connector_center_mm('N01') == 7.5
    assert A.connector_center_mm('N16') == 142.5
    assert A.port_along_mm('N01', 1) == pytest.approx(5.625)
    assert A.port_along_mm('N01', 16) == pytest.approx(9.375)
    assert A.port_along_mm('N16', 16) == pytest.approx(144.375)
    assert A.port_along_mm('E05', 9) - A.port_along_mm('E05', 8) == pytest.approx(0.25)
    # edge projection (z dropped)
    assert A.edge_xy('N', 10.0) == [10.0, 150.0]
    assert A.edge_xy('S', 10.0) == [10.0, 0.0]
    assert A.edge_xy('E', 10.0) == [150.0, 10.0]
    assert A.edge_xy('W', 10.0) == [0.0, 10.0]
    assert A.inward_vector('N') == [0.0, -1.0]
    assert A.inward_vector('S') == [0.0, 1.0]
    assert A.inward_vector('E') == [-1.0, 0.0]
    assert A.inward_vector('W') == [1.0, 0.0]


def test_csv_hashes_and_topology_detection(state_v1, state_v2):
    assert state_v1['csv_sha256'] == A.V1_SHA256
    assert state_v2['csv_sha256'] == A.V2_SHA256
    assert state_v1['topology'] == 'V1'
    assert state_v2['topology'] == 'V2'
    assert A.detect_topology(A.V1_CSV) == 'V1'
    assert A.detect_topology(A.V2_CSV) == 'V2'


# ---------------------------------------------------------------------------
# 2. CSV / relation / row->plane rules
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('fixture_name', ['state_v1', 'state_v2'])
def test_connections_rows_and_planes(fixture_name, request):
    state = request.getfixturevalue(fixture_name)
    validation = state['validation']
    checks = validation['checks']
    assert validation['passed'] is True
    assert validation['failed_checks'] == []
    assert state['validation']['port_model'] == A.PORT_MODEL
    assert checks['connections']['observed'] == 1024
    assert checks['route_ids']['unique'] == 1024
    assert checks['relation_counts']['observed']['opposite'] == 512
    assert checks['relation_counts']['observed']['adjacent'] == 512
    assert checks['pair_counts']['observed'] == {
        'NS': 256, 'EW': 256, 'EN': 128, 'ES': 128, 'SW': 128, 'NW': 128}
    assert checks['different_sides']['same_side_connections'] == 0
    assert checks['row_rule']['violations'] == 0
    assert checks['relation_label']['violations'] == 0
    assert checks['channel_formula']['violations'] == 0
    assert checks['no_duplicate_connection']['duplicates'] == 0
    # per plane: row 1 -> z1 opposite, row 2 -> z2 adjacent
    z1, z2 = validation['planes']['z1'], validation['planes']['z2']
    for plane, entry, relation, row in (('z1', z1, 'opposite', 1),
                                        ('z2', z2, 'adjacent', 2)):
        assert entry['passed'] is True
        assert entry['row'] == row
        assert entry['z_mm'] == A.PLANE_Z_MM[row]
        assert entry['connections'] == 512
        assert entry['endpoints'] == 1024
        assert entry['distinct_endpoints'] == 1024
        assert entry['port_keys'] == entry['expected_ports'] == 1024
        assert entry['ports_missing'] == 0
        assert entry['ports_duplicated'] == 0
        assert entry['relations'] == ({'opposite': 512, 'adjacent': 0}
                                      if relation == 'opposite'
                                      else {'opposite': 0, 'adjacent': 512})
        assert entry['cross_plane_row_violations'] == 0
        assert entry['height_violations'] == 0
        assert entry['inward_violations'] == 0
        assert entry['along_formula_max_error_mm'] <= A.TOL_MM
        assert entry['routing_xy_max_error_mm'] <= A.TOL_MM


def test_endpoint_identities_are_the_2048_real_fibers(state_v1):
    validation = state_v1['validation']
    checks = validation['checks']
    assert checks['endpoints_used_once']['distinct'] == 2048
    assert checks['endpoints_used_once']['usage_min'] == 1
    assert checks['endpoints_used_once']['usage_max'] == 1
    assert checks['endpoints']['observed'] == 2048
    assert checks['channel_coverage']['connectors_checked'] == 64
    assert checks['channel_coverage']['channels_each'] == 32
    assert checks['fibers_per_connector']['observed_counts'] == [32]
    assert len(state_v1['endpoints']) == 2048


# ---------------------------------------------------------------------------
# 3. pitches / heights / physical 3D coordinates
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('fixture_name', ['state_v1', 'state_v2'])
def test_pitches_heights_and_physical_ports(fixture_name, request):
    state = request.getfixturevalue(fixture_name)
    validation = state['validation']
    checks = validation['checks']
    assert checks['column_pitch']['expected_mm'] == 0.25
    assert checks['column_pitch']['max_error_mm'] <= A.TOL_MM
    assert checks['connector_pitch']['expected_mm'] == 9.0
    assert checks['connector_pitch']['first_center_mm'] == 7.5
    assert checks['row_height_separation']['z1_mm'] == 0.0
    assert checks['row_height_separation']['z2_mm'] == 0.5
    assert checks['row_height_separation']['separation_mm'] == 0.5
    assert checks['physical_ports_count']['observed'] == 2048
    ports = state['physical_ports']
    assert len(ports) == 2048
    identities = {(port['connector'], port['row'], port['column']) for port in ports}
    assert len(identities) == 2048
    assert {port['connector'] for port in ports} == {
        f'{side}{number:02d}' for side in A.SIDES
        for number in range(1, A.CONNECTORS_PER_SIDE + 1)}
    faces = {(round(port['x_mm'], 9), round(port['y_mm'], 9)) for port in ports}
    assert len(faces) == 1024, 'two planes must share the 1024 projected XY positions'
    unique_3d = {(round(port['x_mm'], 9), round(port['y_mm'], 9), round(port['z_mm'], 9))
                 for port in ports}
    assert len(unique_3d) == 2048
    assert validation['physical_ports']['unique_3d'] == 2048
    assert validation['physical_ports']['cross_plane_projected_duplicate_ports'] == 1024
    # every port obeys (x, y) on the correct edge and z = z_of_row(row)
    for port in ports:
        side, connector, row, column = port['side'], port['connector'], port['row'], port['column']
        assert port['plane'] == A.plane_of_row(row)
        assert port['z_mm'] == A.z_of_row(row)
        assert port['channel'] == (row - 1) * 16 + column
        expected_along = A.port_along_mm(connector, column)
        assert port['along_mm'] == pytest.approx(expected_along, abs=A.TOL_MM)
        if side == 'N':
            assert port['y_mm'] == 150.0
            assert port['x_mm'] == pytest.approx(expected_along, abs=A.TOL_MM)
        elif side == 'S':
            assert port['y_mm'] == 0.0
        elif side == 'E':
            assert port['x_mm'] == 150.0
        else:
            assert port['x_mm'] == 0.0
    # 3D physical coordinates are NOT the same thing as the 2D routing coordinates:
    # the plane label / z must be carried separately.
    endpoint = state['endpoints']['N01:1:1']
    assert endpoint['routing_xy'] == [5.625, 150.0]
    assert endpoint['z_mm'] == 0.0
    assert endpoint['plane'] == 'z1'
    assert endpoint['physical_row_z_mm'] == 0.0
    endpoint_row2 = state['endpoints']['N01:2:1']
    assert endpoint_row2['routing_xy'] == [5.625, 150.0], 'same XY projection, different z'
    assert endpoint_row2['z_mm'] == 0.5
    assert endpoint_row2['plane'] == 'z2'


def test_mechanical_envelope_warning_retained(state_v1):
    warning = state_v1['validation']['checks']['mechanical_envelope_warning']
    assert warning['warning'] is True
    assert warning['envelope_width_mm'] == 12.59
    assert warning['connector_pitch_mm'] == 9.0
    assert warning['adjacent_envelope_overlap_mm'] == pytest.approx(3.59)
    assert any('9 mm connector pitch' in text for text in state_v1['validation']['warnings'])


def test_previous_round_physical_projection_crosscheck(state_v1):
    check = state_v1['validation']['checks']['previous_round_physical_projection']
    if check.get('skipped'):
        pytest.skip('previous-round endpoints.json not available')
    assert check['passed'] is True
    assert check['checked'] == 2048
    assert check['max_delta_mm'] <= A.MATCH_TOL_MM
    assert check['max_face_u_delta_mm'] <= A.MATCH_TOL_MM


def test_lead_config_constants_match(state_v1):
    check = state_v1['validation']['checks']['lead_config_constants']
    if check.get('skipped'):
        pytest.skip('fslw/config.py not importable')
    assert check['mismatches'] == []


def test_audit_module_is_independent_of_lead_and_previous_round_modules():
    """ports_audit.py must not import fslw/ports.py nor four_side_1024.inputs."""
    code = ('import sys; '
            'from four_side_1024.fslw import ports_audit as A; '
            'A.derive_ports(A.V1_CSV); '
            "print(int('four_side_1024.fslw.ports' in sys.modules), "
            "int('four_side_1024.inputs' in sys.modules))")
    completed = subprocess.run([sys.executable, '-c', code], cwd=str(A.CODE_DIR),
                               capture_output=True, text=True, timeout=300)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == '0 0'


# ---------------------------------------------------------------------------
# 4. negative controls
# ---------------------------------------------------------------------------
def _validate(state, routes, endpoints=None, physical_ports=None):
    return A.validate_dual_height(
        routes,
        endpoints if endpoints is not None else state['endpoints'],
        state['connectors'],
        physical_ports if physical_ports is not None else state['physical_ports'],
        topology=state['topology'], csv_path=A.V1_CSV,
        csv_sha256=state['csv_sha256'])


def test_negative_control_row_plane_mismatch(state_v1):
    routes = copy.deepcopy(state_v1['routes'])
    opp = next(route for route in routes if route['relation'] == 'opposite')
    for role in ('source', 'target'):
        column = int(opp[f'{role}_column'])
        opp[f'{role}_row'] = 2
        opp[f'{role}_channel'] = 16 + column
    opp['row'] = 2
    opp['plane'] = 'z2'
    validation = _validate(state_v1, routes)
    assert validation['passed'] is False
    assert 'row_rule' in validation['failed_checks']
    assert validation['checks']['row_rule']['violations'] >= 1
    assert 'plane_z1' in validation['failed_checks']
    assert 'plane_z2' in validation['failed_checks']


def test_negative_control_duplicate_port(state_v1):
    routes = copy.deepcopy(state_v1['routes'])
    plane_route = next(route for route in routes if route['row'] == 1)
    other = next(route for route in routes
                 if route['row'] == 1 and route['route_id'] != plane_route['route_id'])
    for role in ('connector', 'row', 'column', 'channel'):
        other[f'source_{role}'] = plane_route[f'source_{role}']
    other['source_endpoint'] = plane_route['source_endpoint']
    validation = _validate(state_v1, routes)
    assert validation['passed'] is False
    assert 'endpoints_used_once' in validation['failed_checks']
    assert 'plane_z1' in validation['failed_checks']


def test_negative_control_tampered_physical_coordinates(state_v1):
    ports = copy.deepcopy(state_v1['physical_ports'])
    ports[0]['x_mm'] = ports[0]['x_mm'] + 0.01
    validation = _validate(state_v1, state_v1['routes'], physical_ports=ports)
    assert validation['passed'] is False
    assert 'physical_coordinates' in validation['failed_checks']
    assert validation['checks']['physical_coordinates']['max_coordinate_error_mm'] > 0


def test_negative_control_duplicate_physical_port_identity(state_v1):
    ports = copy.deepcopy(state_v1['physical_ports'])
    # make the first two ports collide on (connector, row, column)
    ports[1] = dict(ports[0])
    ports[1]['topology'] = ports[0]['topology']
    validation = _validate(state_v1, state_v1['routes'], physical_ports=ports)
    assert validation['passed'] is False
    assert 'physical_port_identities' in validation['failed_checks']


def test_negative_control_row_plane_mismatch_in_endpoints(state_v1):
    endpoints = copy.deepcopy(state_v1['endpoints'])
    endpoints['N01:1:1'] = dict(endpoints['N01:1:1'])
    endpoints['N01:1:1']['plane'] = 'z2'
    endpoints['N01:1:1']['z_mm'] = 0.5
    validation = _validate(state_v1, state_v1['routes'], endpoints=endpoints)
    assert validation['passed'] is False
    assert 'plane_z1' in validation['failed_checks']
    assert validation['checks']['plane_z1']['height_violations'] >= 1


# ---------------------------------------------------------------------------
# 5. comparison with Lead's fslw/ports.py
# ---------------------------------------------------------------------------
def test_comparison_with_lead_ports(comparison):
    assert comparison['lead_ports_available'] is True
    summary = comparison['summary']
    assert summary['passed'] is True
    assert summary['endpoints_compared'] == 2048
    assert summary['endpoint_identity_sets_equal'] is True
    assert comparison['endpoint_identity_sets_equal'] is True
    assert comparison['missing_in_lead'] == []
    assert comparison['extra_in_lead'] == []
    # the task requires max |delta| == 0 (or the exact deviation reported)
    assert summary['max_routing_xy_delta_mm'] == 0.0
    assert summary['max_physical_along_delta_mm'] == 0.0
    assert summary['max_z_delta_mm'] == 0.0
    assert summary['endpoint_plane_violations'] == 0
    assert summary['row_plane_violations'] == {'V1': 0, 'V2': 0}
    assert summary['route_field_mismatches'] == {'V1': 0, 'V2': 0}
    assert summary['physical_table_max_delta_mm'] == {'V1': 0.0, 'V2': 0.0}
    for topology in ('V1', 'V2'):
        entry = comparison['topologies'][topology]
        assert entry['route_id_sets_equal'] is True
        for plane in ('z1', 'z2'):
            plane_entry = entry['planes'][plane]
            assert plane_entry['route_id_sets_equal'] is True
            assert plane_entry['endpoint_set_mismatches'] == 0
            assert plane_entry['max_routing_xy_delta_mm'] == 0.0


# ---------------------------------------------------------------------------
# 6. artifact build
# ---------------------------------------------------------------------------
def test_build_all_artifacts(tmp_path):
    result = A.build_all(tmp_path, plots=True, compare=True)
    summary = result['summary']
    assert summary['v1_validation_passed'] is True
    assert summary['v2_validation_passed'] is True
    assert summary['lead_ports_comparison']['passed'] is True
    expected_files = [
        'ports_validation_v1.json', 'ports_validation_v2.json',
        'physical_ports_v1.csv', 'physical_ports_v2.csv',
        'plane_connectivity_v1_z1.png', 'plane_connectivity_v1_z2.png',
        'plane_connectivity_v2_z1.png', 'plane_connectivity_v2_z2.png',
        'dual_height_schematic.png', 'lead_ports_comparison.json', 'README.md',
    ]
    for name in expected_files:
        path = tmp_path / name
        assert path.exists() and path.stat().st_size > 0, name
    validation = json.loads((tmp_path / 'ports_validation_v1.json').read_text(
        encoding='utf-8'))
    assert validation['passed'] is True
    assert validation['port_model'] == 'real_2x16_dual_height'
    assert validation['physical_ports']['count'] == 2048
    with (tmp_path / 'physical_ports_v1.csv').open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2048
    for column in A.PHYSICAL_PORT_COLUMNS:
        assert column in rows[0]
    assert {row['plane'] for row in rows} == {'z1', 'z2'}
    assert {row['row'] for row in rows} == {'1', '2'}
    readme = (tmp_path / 'README.md').read_text(encoding='utf-8')
    for phrase in REQUIRED_README_PHRASES:
        assert phrase in readme, phrase
    comparison = json.loads((tmp_path / 'lead_ports_comparison.json').read_text(
        encoding='utf-8'))
    assert comparison['summary']['passed'] is True
    assert comparison['summary']['max_routing_xy_delta_mm'] == 0.0
