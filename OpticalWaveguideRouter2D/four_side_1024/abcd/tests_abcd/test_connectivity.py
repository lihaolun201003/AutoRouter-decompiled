"""Phase-1 acceptance tests for ``four_side_1024/abcd/connectivity.py``.

Covers:
* both CSVs load through the UNCHANGED legacy ``four_side_1024.inputs.load``
  (the fixed assertions inside it must pass for V2 as well);
* ``load_topology`` extended validation record;
* all independent CSV/endpoint numbering checks;
* V1/V2 symmetry claims (8 D4 transforms, connector level vs endpoint level);
* negative controls: tampered routes / endpoints must NOT be reported symmetric;
* the V1-vs-V2 diff numbers;
* the artifact build (JSON/CSV/MD/PNG).

Run from the code directory ``OpticalWaveguideRouter2D``::

    .\\.venv\\Scripts\\python.exe -m pytest four_side_1024\\abcd\\tests_abcd\\test_connectivity.py -q
"""
import copy
import csv
import json
from pathlib import Path

import pytest

from four_side_1024 import inputs
from four_side_1024.abcd import connectivity as C

CSV_AVAILABLE = C.V1_CSV.exists() and C.V2_CSV.exists()
pytestmark = pytest.mark.skipif(not CSV_AVAILABLE, reason='V1/V2 connectivity CSV not found')

TRANSFORM_NAMES = ['identity', 'rot90', 'rot180', 'rot270',
                   'mirror_x', 'mirror_y', 'diag_main', 'diag_anti']


# ---------------------------------------------------------------------------
# module-scoped fixtures (loading is deterministic and a bit expensive)
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def topology_v1():
    return C.load_topology(C.V1_CSV)


@pytest.fixture(scope='module')
def topology_v2():
    return C.load_topology(C.V2_CSV)


@pytest.fixture(scope='module')
def symmetry_v1(topology_v1):
    routes, endpoints, _connectors, _validation = topology_v1
    return C.symmetry_maps(routes, endpoints)


@pytest.fixture(scope='module')
def symmetry_v2(topology_v2):
    routes, endpoints, _connectors, _validation = topology_v2
    return C.symmetry_maps(routes, endpoints)


@pytest.fixture(scope='module')
def diff(topology_v1, topology_v2):
    routes1, endpoints1, _c1, _v1 = topology_v1
    routes2, endpoints2, _c2, _v2 = topology_v2
    return C.diff_topologies(routes1, endpoints1, routes2, endpoints2)


# ---------------------------------------------------------------------------
# 1. input files + unchanged legacy loader
# ---------------------------------------------------------------------------
def test_v1_csv_sha256_matches_spec():
    assert C.sha256_file(C.V1_CSV) == C.V1_SHA256


def test_v2_csv_sha256_is_recorded_and_stable():
    # SPEC §1: connectivity.py computes and records the V2 hash.
    assert C.sha256_file(C.V2_CSV) == C.V2_SHA256
    assert C.detect_topology(C.V1_CSV) == 'V1'
    assert C.detect_topology(C.V2_CSV) == 'V2'


@pytest.mark.parametrize('path,expected_topology', [(C.V1_CSV, 'V1'), (C.V2_CSV, 'V2')])
def test_inputs_load_passes_unchanged(path, expected_topology):
    """Prove the fixed assertions inside legacy ``inputs.load`` accept both CSVs."""
    routes, endpoints, connectors, validation = inputs.load(path)
    # reaching here means every fixed assert inside inputs.load passed
    assert len(routes) == 1024
    assert validation['passed'] is True
    assert validation['connections'] == 1024
    assert validation['endpoints_used_once'] is True
    assert validation['unique_physical_identities'] == 2048
    assert validation['opposite'] == 512
    assert validation['adjacent'] == 512
    assert validation['connectors'] == 64
    assert validation['channels_per_connector'] == 32
    assert validation['csv_sha256'] == (C.V1_SHA256 if expected_topology == 'V1' else C.V2_SHA256)
    assert len(endpoints) == 2048
    assert len(connectors) == 64
    # fixed assertion values, verified again here (they are what inputs.load asserts)
    assert sorted(int(r['route_id']) for r in routes) == list(range(1, 1025))
    assert all(r['source_row'] == r['target_row'] == 1
               for r in routes if r['relation'] == 'opposite')
    assert all(r['source_row'] == r['target_row'] == 2
               for r in routes if r['relation'] == 'adjacent')


def _parse_endpoint_id(endpoint_id):
    """'N01:1:3' -> (side is not encoded, connector, row, column, channel)."""
    connector, row, column = endpoint_id.split(':')
    row, column = int(row), int(column)
    return connector, row, column, (row - 1) * 16 + column


def test_load_topology_extends_validation_without_mutating_inputs(topology_v1, topology_v2):
    for fixture, topology, path, sha in (
            (topology_v1, 'V1', C.V1_CSV, C.V1_SHA256),
            (topology_v2, 'V2', C.V2_CSV, C.V2_SHA256)):
        routes, endpoints, connectors, validation = fixture
        assert validation['topology'] == topology
        assert Path(validation['csv_path']) == path.resolve()
        assert validation['csv_sha256'] == sha
        assert validation['known_csv_sha256'] is True
        evidence = validation['inputs_load_evidence']
        assert evidence['returned_without_assertion_error'] is True
        assert evidence['rows'] == 1024
        assert evidence['relation_counts'] == {'adjacent': 512, 'opposite': 512}
        assert evidence['endpoints_used_once'] is True
        assert evidence['virtual_routing_xy_unique'] == 2048
        assert validation['checks_passed'] is True
        # inputs.load output itself is unchanged in shape
        assert isinstance(routes, list) and isinstance(endpoints, dict) and len(connectors) == 64


def test_load_topology_accepts_cfg(topology_v2):
    cfg = inputs.config()
    routes, endpoints, _connectors, validation = C.load_topology(C.V2_CSV, cfg=cfg)
    assert len(routes) == 1024 and len(endpoints) == 2048
    assert validation['checks_passed'] is True


# ---------------------------------------------------------------------------
# 2. independent CSV / endpoint numbering checks
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('fixture_name', ['topology_v1', 'topology_v2'])
def test_validate_csv_checks_all_required_checks(fixture_name, request):
    routes, endpoints, connectors, validation = request.getfixturevalue(fixture_name)
    checks = C.validate_csv_checks(routes, endpoints=endpoints, connectors=connectors)
    assert checks['passed'] is True
    assert checks['failed_checks'] == []
    inner = checks['checks']
    assert inner['connections']['observed'] == 1024
    assert inner['route_ids']['unique'] == 1024
    assert inner['endpoints_used_once']['distinct_endpoints'] == 2048
    assert inner['endpoints_used_once']['usage_min'] == 1
    assert inner['endpoints_used_once']['usage_max'] == 1
    assert inner['connectors']['observed'] == 64
    assert inner['channel_coverage']['connectors_ok'] == 64
    assert inner['channel_coverage']['expected_channels_per_connector'] == 32
    assert inner['different_sides']['same_side_connections'] == 0
    assert inner['relation_counts']['observed'] == {'opposite': 512, 'adjacent': 512}
    assert inner['pair_counts']['observed'] == {'NS': 256, 'EW': 256, 'EN': 128,
                                                'ES': 128, 'SW': 128, 'NW': 128}
    assert inner['ordered_side_pair_counts']['observed'] == {
        'N->S': 256, 'E->W': 256, 'N->E': 128, 'E->S': 128, 'S->W': 128, 'W->N': 128}
    assert inner['row_rule']['violations'] == 0
    assert inner['channel_formula']['violations'] == 0
    assert inner['connector_format']['violations'] == 0
    assert inner['no_duplicate_connection']['distinct_unordered'] == 1024
    assert inner['no_duplicate_connection']['duplicate_unordered'] == 0
    assert inner['endpoint_coordinates_unique']['distinct'] == 2048
    assert inner['endpoint_coordinates_unique']['duplicates'] == 0
    assert inner['endpoint_geometry']['violations'] == 0
    assert inner['endpoint_geometry']['max_xy_error_mm'] <= C.MATCH_TOL_MM
    assert inner['endpoint_on_edge']['violations'] == 0
    assert inner['endpoint_identity_matches_csv']['violations'] == 0
    # the same record is embedded in the extended validation
    assert validation['checks']['passed'] is True


def test_validate_csv_checks_without_endpoints_skips_geometry(topology_v1):
    routes = topology_v1[0]
    checks = C.validate_csv_checks(routes)
    assert checks['passed'] is True
    assert checks['checks']['endpoint_geometry']['skipped'] is True


def test_validate_negative_control_duplicate_endpoint(topology_v1):
    routes = copy.deepcopy(topology_v1[0])
    source = routes[0]['source_endpoint']
    connector, row, column, channel = _parse_endpoint_id(source)
    routes[1]['source_endpoint'] = source
    routes[1].update(source_side=routes[0]['source_side'], source_connector=connector,
                     source_row=row, source_column=column, source_channel=channel)
    # also duplicate the whole connection -> duplicate unordered endpoint pair
    for field in ('target_side', 'target_connector', 'target_row',
                  'target_column', 'target_channel', 'target_endpoint'):
        routes[1][field] = routes[0][field]
    checks = C.validate_csv_checks(routes)
    assert checks['passed'] is False
    assert 'endpoints_used_once' in checks['failed_checks']
    assert 'no_duplicate_connection' in checks['failed_checks']
    assert checks['checks']['no_duplicate_connection']['duplicate_unordered'] >= 1


def test_validate_negative_control_same_side_connection(topology_v1):
    routes = copy.deepcopy(topology_v1[0])
    routes[0].update(target_side=routes[0]['source_side'],
                     target_connector=routes[0]['source_connector'],
                     target_row=routes[0]['source_row'],
                     target_column=routes[0]['source_column'],
                     target_channel=routes[0]['source_channel'])
    checks = C.validate_csv_checks(routes)
    assert checks['passed'] is False
    assert 'different_sides' in checks['failed_checks']


def test_validate_negative_control_channel_formula(topology_v1):
    routes = copy.deepcopy(topology_v1[0])
    route = routes[0]
    route['target_channel'] = 32 if route['target_channel'] != 32 else 31
    checks = C.validate_csv_checks(routes)
    assert checks['passed'] is False
    assert 'channel_formula' in checks['failed_checks']


# ---------------------------------------------------------------------------
# 3. symmetry: contract and measured claims
# ---------------------------------------------------------------------------
def test_symmetry_transform_set_and_definitions(symmetry_v2):
    assert [t['name'] for t in symmetry_v2['transforms']] == TRANSFORM_NAMES
    expected = {
        'identity': ([[1, 0], [0, 1]], [0, 0]),
        'rot90': ([[0, -1], [1, 0]], [150, 0]),
        'rot180': ([[-1, 0], [0, -1]], [150, 150]),
        'rot270': ([[0, 1], [-1, 0]], [0, 150]),
        'mirror_x': ([[-1, 0], [0, 1]], [150, 0]),
        'mirror_y': ([[1, 0], [0, -1]], [0, 150]),
        'diag_main': ([[0, 1], [1, 0]], [0, 0]),
        'diag_anti': ([[0, -1], [-1, 0]], [150, 150]),
    }
    for transform in symmetry_v2['transforms']:
        assert transform['matrix'] == expected[transform['name']][0]
        assert transform['offset'] == expected[transform['name']][1]
        for key in ('route_map', 'route_map_complete', 'mapped_route_count',
                    'channel_map_consistent'):
            assert key in transform
        assert len(transform['route_map']) == 1024
        assert all(isinstance(k, int) for k in transform['route_map'])
    # SPEC §5 alias
    assert symmetry_v2['aliases'] == {'diag': 'diag_main'}
    assert symmetry_v2['by_name']['diag'] is symmetry_v2['by_name']['diag_main']
    assert symmetry_v2['tolerance_mm'] == C.MATCH_TOL_MM
    assert symmetry_v2['n_routes'] == 1024 and symmetry_v2['n_endpoints'] == 2048


def test_symmetry_geometry_is_exact(symmetry_v1, symmetry_v2):
    for symmetry, expected_connector_pairs in ((symmetry_v1, 1024), (symmetry_v2, 384)):
        for transform in symmetry['transforms']:
            assert transform['endpoint_map_complete'] is True
            assert transform['snap_max_error_mm'] <= C.MATCH_TOL_MM
            assert transform['connector_map_complete'] is True
            assert transform['connector_pairs_total'] == expected_connector_pairs
            assert transform['connector_snap_max_error_mm'] <= C.MATCH_TOL_MM


def test_symmetry_v2_claims(symmetry_v2):
    # connector level: connection multiset invariant under every D4 transform
    assert symmetry_v2['connector_level_symmetric'] == TRANSFORM_NAMES
    for transform in symmetry_v2['transforms']:
        assert transform['connector_pair_multiset_preserved'] is True
        assert transform['connector_pair_violations'] == 0
        assert transform['connector_map_complete'] is True
    # endpoint/route level: only identity and the main-diagonal mirror survive
    assert symmetry_v2['endpoint_level_symmetric'] == ['identity', 'diag_main']
    assert symmetry_v2['route_level_mapped_counts'] == {
        'identity': 1024, 'rot90': 256, 'rot180': 0, 'rot270': 256,
        'mirror_x': 256, 'mirror_y': 256, 'diag_main': 1024, 'diag_anti': 0}
    # rot180/diag_anti flip the virtual row: no endpoint-level route can match
    assert symmetry_v2['by_name']['rot180']['mapped_route_count'] == 0
    assert symmetry_v2['by_name']['rot180']['row_map'] == {1: 2, 2: 1}
    assert symmetry_v2['by_name']['diag_main']['fixed_point_count'] == 64
    # pure (side-independent) channel permutation exists only for these four
    assert symmetry_v2['channel_map_pure'] == ['identity', 'rot180', 'diag_main', 'diag_anti']
    assert symmetry_v2['by_name']['diag_main']['channel_map'] == {ch: ch for ch in range(1, 33)}
    assert symmetry_v2['by_name']['rot180']['channel_map'] == {
        ch: 33 - ch for ch in range(1, 33)}
    # rot90 maps channels identically on N/S connectors but mirrored on E/W ones
    rot90 = symmetry_v2['by_name']['rot90']
    assert rot90['channel_map_consistent'] is False
    assert rot90['channel_map_by_side_consistent'] is True
    assert rot90['channel_map_by_side']['N'] == {ch: ch for ch in range(1, 33)}
    assert rot90['channel_map_by_side']['E'] == {ch: 33 - ch for ch in range(1, 33)}
    assert rot90['side_map'] == {'N': 'W', 'W': 'S', 'S': 'E', 'E': 'N'}


def test_symmetry_v1_claims(symmetry_v1):
    assert symmetry_v1['endpoint_level_symmetric'] == ['identity']
    assert symmetry_v1['connector_level_symmetric'] == ['identity', 'diag_anti']
    assert symmetry_v1['route_level_mapped_counts'] == {
        'identity': 1024, 'rot90': 256, 'rot180': 0, 'rot270': 256,
        'mirror_x': 256, 'mirror_y': 256, 'diag_main': 512, 'diag_anti': 0}
    assert symmetry_v1['by_name']['diag_main']['route_map_complete'] is False
    assert symmetry_v1['by_name']['diag_anti']['connector_pair_multiset_preserved'] is True


def test_symmetry_route_map_matches_transformed_endpoints(topology_v2, symmetry_v2):
    routes, endpoints, _connectors, _validation = topology_v2
    pair_to_route = {tuple(sorted((r['source_endpoint'], r['target_endpoint']))): r['route_id']
                     for r in routes}
    transform = symmetry_v2['by_name']['diag_main']
    assert transform['route_map_complete'] is True
    for r in routes:
        image_id = transform['route_map'][r['route_id']]
        image = next(other for other in routes if other['route_id'] == image_id)
        orientation = transform['orientation'][r['route_id']]
        if orientation == 'direct':
            role_pairs = (('source', 'source'), ('target', 'target'))
        else:
            role_pairs = (('source', 'target'), ('target', 'source'))
        for role_src, role_dst in role_pairs:
            xy = endpoints[r[f'{role_src}_endpoint']]['routing_xy']
            expected = C.apply_transform(transform, xy)
            image_xy = endpoints[image[f'{role_dst}_endpoint']]['routing_xy']
            assert max(abs(expected[0] - image_xy[0]),
                       abs(expected[1] - image_xy[1])) <= C.MATCH_TOL_MM, r['route_id']
    # routes.json-style records (no CSV-only fields) give the same route map
    stripped = [dict(route_id=r['route_id'], source_endpoint=r['source_endpoint'],
                     target_endpoint=r['target_endpoint'], status='routed')
                for r in routes]
    symmetry_stripped = C.symmetry_maps(stripped, endpoints)
    assert symmetry_stripped['by_name']['diag_main']['route_map'] == transform['route_map']
    assert symmetry_stripped['route_level_mapped_counts'] == symmetry_v2['route_level_mapped_counts']


def test_symmetry_negative_control_swapped_targets(topology_v2):
    routes, endpoints, _connectors, _validation = topology_v2
    tampered = copy.deepcopy(routes)
    # swap the target endpoints of two routes with different sources AND different
    # target connectors -> both the endpoint-level and connector-level symmetry break
    source_a = [r for r in tampered if r['source_connector'] == 'N01']
    source_b = [r for r in tampered if r['source_connector'] == 'N05']
    route_a, route_b = next((a, b) for a in source_a for b in source_b
                            if a['target_connector'] != b['target_connector'])
    route_a['target_endpoint'], route_b['target_endpoint'] = (
        route_b['target_endpoint'], route_a['target_endpoint'])
    for route in (route_a, route_b):
        connector, row, column, channel = _parse_endpoint_id(route['target_endpoint'])
        route.update(target_side=connector[0], target_connector=connector,
                     target_row=row, target_column=column, target_channel=channel)
    symmetry = C.symmetry_maps(tampered, endpoints)
    assert symmetry['by_name']['diag_main']['route_map_complete'] is False
    assert symmetry['endpoint_level_symmetric'] == ['identity']
    assert any(not t['connector_pair_multiset_preserved'] for t in symmetry['transforms']
               if t['name'] != 'identity')
    assert symmetry['connector_level_symmetric'] != TRANSFORM_NAMES
    # identity is still a trivial symmetry of any route set
    assert symmetry['by_name']['identity']['route_map_complete'] is True


def test_symmetry_negative_control_shifted_endpoint(topology_v2):
    routes, endpoints, _connectors, _validation = topology_v2
    tampered = copy.deepcopy(endpoints)
    key = sorted(tampered)[0]
    tampered[key] = dict(tampered[key])
    tampered[key]['routing_xy'] = [tampered[key]['routing_xy'][0] + 0.01,
                                   tampered[key]['routing_xy'][1]]
    symmetry = C.symmetry_maps(routes, tampered)
    # identity still snaps each (shifted) coordinate to itself and remains a trivial
    # symmetry, but any non-trivial transform must fail on the shifted endpoint.
    assert symmetry['by_name']['identity']['route_map_complete'] is True
    for name in ('rot90', 'rot180', 'rot270', 'mirror_x', 'mirror_y',
                 'diag_main', 'diag_anti'):
        transform = symmetry['by_name'][name]
        assert transform['endpoint_map_complete'] is False, name
        assert transform['route_map_complete'] is False, name
    assert symmetry['endpoint_level_symmetric'] == ['identity']


# ---------------------------------------------------------------------------
# 4. V1 vs V2 diff
# ---------------------------------------------------------------------------
def test_diff_v1_v2_numbers(diff):
    summary = diff['summary']
    assert summary['v1_connections'] == summary['v2_connections'] == 1024
    assert summary['v1_distinct_endpoint_pairs'] == summary['v2_distinct_endpoint_pairs'] == 1024
    assert summary['identical_connections'] == 8
    assert summary['identical_ordered_connections'] == 8
    assert summary['v1_only_connections'] == summary['v2_only_connections'] == 1016
    assert summary['v1_connector_pairs'] == 1024
    assert summary['v2_connector_pairs'] == 384
    assert summary['common_connector_pairs'] == 272
    assert summary['v1_only_connector_pairs'] == 752
    assert summary['v2_only_connector_pairs'] == 112
    assert summary['v1_multiplicity_dist'] == {'1': 1024}
    assert summary['v2_multiplicity_dist'] == {'2': 256, '4': 128}
    assert summary['v1_distinct_neighbours_per_connector'] == [32]
    assert summary['v2_distinct_neighbours_per_connector'] == [12]
    assert summary['degree_change_dist'] == {'0': 64}
    assert summary['source_remap_class_counts'] == {'0': 8, '1': 34, '2': 982}
    assert summary['change_classes'] == {'identical': 8,
                                         'same_connector_pair_channel_changed': 60,
                                         'same_source_connector': 956}
    relation = diff['by_relation']
    assert relation['NS']['common_endpoint_pairs'] == 4
    assert relation['EW']['common_endpoint_pairs'] == 4
    assert all(relation[key]['common_endpoint_pairs'] == 0 for key in ('EN', 'ES', 'SW', 'NW'))
    assert relation['NS']['common_connector_pairs'] == 64
    assert relation['EW']['common_connector_pairs'] == 64
    assert relation['EN']['common_connector_pairs'] == 40
    assert relation['SW']['common_connector_pairs'] == 40
    assert relation['ES']['common_connector_pairs'] == 32
    assert relation['NW']['common_connector_pairs'] == 32
    # channel remapping evidence
    usage = diff['channel_usage_by_side_pair']
    assert usage['N->E']['v1_source_channels'] == list(range(17, 25))
    assert usage['N->E']['v2_source_channels'] == list(range(25, 33))
    assert usage['N->S']['v2_source_channels'] == list(range(1, 17))
    assert usage['S->W']['v1_target_channels'] == list(range(25, 33))
    assert usage['S->W']['v2_target_channels'] == list(range(17, 25))
    assert len(diff['identical_connections']) == 8
    identical_ids = {row['route_id_v1'] for row in diff['identical_connections']}
    assert identical_ids == {1, 86, 171, 256, 257, 342, 427, 512}


# ---------------------------------------------------------------------------
# 5. artifacts
# ---------------------------------------------------------------------------
def test_build_connectivity_artifacts(tmp_path):
    result = C.build_connectivity_artifacts(tmp_path, plots=True)
    summary = result['summary']
    assert summary['v1_checks_passed'] is True
    assert summary['v2_checks_passed'] is True
    assert summary['v2_endpoint_level_symmetric'] == ['identity', 'diag_main']
    assert summary['v2_connector_level_symmetric'] == TRANSFORM_NAMES
    for name in ('validation_v1.json', 'validation_v2.json', 'symmetry_v1.json',
                 'symmetry_v2.json', 'validation.json', 'diff_v1_v2.csv', 'diff_v1_v2.md',
                 'connectivity_v1.png', 'connectivity_v2.png', 'diff_heatmap.png',
                 'v2_symmetry_diagram.png'):
        path = tmp_path / name
        assert path.exists() and path.stat().st_size > 0, name
    validation_v2 = json.loads((tmp_path / 'validation_v2.json').read_text(encoding='utf-8'))
    assert validation_v2['topology'] == 'V2'
    assert validation_v2['checks_passed'] is True
    assert validation_v2['csv_sha256'] == C.V2_SHA256
    symmetry_v2 = json.loads((tmp_path / 'symmetry_v2.json').read_text(encoding='utf-8'))
    assert [t['name'] for t in symmetry_v2['transforms']] == TRANSFORM_NAMES
    assert symmetry_v2['summary']['route_level_symmetric'] == ['identity', 'diag_main']
    with (tmp_path / 'diff_v1_v2.csv').open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1024
    assert sum(1 for row in rows if row['change_class'] == 'identical') == 8
    markdown = (tmp_path / 'diff_v1_v2.md').read_text(encoding='utf-8')
    assert 'V1 vs V2 连接拓扑差异表' in markdown
    assert '| 两版完全相同的连接（无序端点对） | 8 |' in markdown
