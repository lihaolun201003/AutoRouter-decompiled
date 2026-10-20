"""Acceptance tests for the T1 V2 dual-height 698-channel BASE baseline.

These tests validate the *already produced* artefacts under
``outputs/four_side_1024_v2_candidate_rr_v01`` (regenerate them with
``.venv\\Scripts\\python.exe four_side_1024\\v2opt\\audit_baseline.py``) and add a
light-weight independent re-check on top of the full acceptance script.

Run from ``OpticalWaveguideRouter2D``::

    .venv\\Scripts\\python.exe -m pytest four_side_1024\\v2opt\\tests -q
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from four_side_1024.d56 import index as d56_index  # noqa: E402
from four_side_1024.fslw import config as fslw_config  # noqa: E402
from four_side_1024.fslw import crosscheck_fslw  # noqa: E402
from four_side_1024.fslw import ports as fslw_ports  # noqa: E402

OUT_ROOT = PROJECT_ROOT / 'outputs' / 'four_side_1024_v2_candidate_rr_v01'
HIST_ROOT = PROJECT_ROOT / 'outputs' / 'four_side_1024_fslw_R40_gap30_abcd'
ACCEPTANCE = OUT_ROOT / 'baseline_acceptance.json'
PLANES = ('z1', 'z2')
EXPECTED_ROUTED = {'z1': 492, 'z2': 206}
EXPECTED_TOTAL_ROUTED = 698
ROUTES_PER_PLANE = 512
CONNECTIONS_TOTAL = 1024
V2_CSV_SHA256 = '49dd9e89c4ea506d04638ae34eb06a0d8163d479de80869804c881ee1c43915e'
SOURCE_ROUTES = {
    'z1': HIST_ROOT / 'planes' / 'V2' / 'D' / 'z1' / 'routes.json',
    'z2': HIST_ROOT / 'planes' / 'V2' / 'C' / 'z2' / 'routes.json',
}
IDENTITY_FIELDS = ('route_id', 'source_endpoint', 'target_endpoint', 'pair',
                   'relation', 'source_side', 'target_side', 'source_row',
                   'target_row')

pytestmark = pytest.mark.skipif(
    not ACCEPTANCE.exists(),
    reason='v01 baseline artefacts missing: run '
           'four_side_1024/v2opt/audit_baseline.py first')


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'))


def plane_dir(plane):
    return OUT_ROOT / 'planes' / 'V2' / 'BASE' / plane


def plane_payload(plane):
    return load_json(plane_dir(plane) / 'routes.json')


def acceptance():
    return load_json(ACCEPTANCE)


def criterion(number):
    for item in acceptance()['criteria']:
        if item['criterion_id'] == number:
            return item
    raise AssertionError(f'acceptance criterion {number} missing')


# ---------------------------------------------------------------------------
# baseline_acceptance.json: the machine-readable verdict itself
# ---------------------------------------------------------------------------
def test_acceptance_json_exists_and_all_criteria_pass():
    payload = acceptance()
    assert payload['schema'].endswith('baseline_acceptance_v1')
    criteria = payload['criteria']
    assert [item['criterion_id'] for item in criteria] == [1, 2, 3, 4, 5, 6, 7]
    assert all(item['passed'] is True for item in criteria), (
        [(item['criterion_id'], item['passed']) for item in criteria])
    summary = payload['summary']
    assert summary['all_criteria_passed'] is True
    assert summary['baseline_698_established'] is True
    assert summary['combined_routed'] == EXPECTED_TOTAL_ROUTED
    assert summary['routing_rate'] == EXPECTED_TOTAL_ROUTED / CONNECTIONS_TOTAL
    assert summary['routing_rate_text'] == '698/1024'
    assert summary['z1_routed'] == 492
    assert summary['z2_routed'] == 206
    assert summary['plane_audit_passed'] == {'z1': True, 'z2': True}
    assert summary['combined_same_plane_violations'] == 0
    assert summary['d56_leave_one_out_violations'] == {'z1': 0, 'z2': 0}
    assert summary['crosscheck_mismatches'] == {'z1': 0, 'z2': 0}


def test_acceptance_recorded_file_hashes_match_disk():
    payload = acceptance()
    files = payload['outputs']['files']
    assert files
    for name, record in files.items():
        path = Path(record['path'])
        assert record['exists'] is True, f'{name}: recorded as missing'
        assert path.exists(), f'{name}: {path} disappeared'
        assert path.stat().st_size == record['bytes'], f'{name}: size changed'
        assert sha256_file(path) == record['sha256'], f'{name}: sha256 changed'


# ---------------------------------------------------------------------------
# criterion 1: frozen CSV identity + sha256, 512 records per plane
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('plane', PLANES)
def test_plane_records_identity_matches_frozen_csv(plane):
    payload = plane_payload(plane)
    records = payload['routes']
    assert len(records) == ROUTES_PER_PLANE
    csv_routes, _endpoints, _connectors, validation = fslw_ports.load_plane(
        'V2', plane)
    by_id = {route['route_id']: route for route in csv_routes}
    assert [record['route_id'] for record in records] == [
        route['route_id'] for route in csv_routes]
    for record in records:
        source = by_id[record['route_id']]
        for field in IDENTITY_FIELDS:
            assert record.get(field) == source.get(field), (
                f'{plane} route {record["route_id"]} field {field}: '
                f'{record.get(field)!r} != {source.get(field)!r}')
        assert record['plane'] == plane
        assert record['z_mm'] == fslw_config.PLANE_Z_MM[
            fslw_config.PLANE_ROW[plane]]
    statuses = Counter(record['status'] for record in records)
    assert statuses['routed'] == EXPECTED_ROUTED[plane]
    assert validation['passed'] is True
    assert validation['csv_sha256'] == V2_CSV_SHA256
    assert payload['csv_sha256'] == V2_CSV_SHA256
    csv_path = Path(validation['csv_path'])
    assert csv_path.exists()
    assert sha256_file(csv_path) == V2_CSV_SHA256


@pytest.mark.parametrize('plane', PLANES)
def test_plane_payload_provenance(plane):
    payload = plane_payload(plane)
    assert payload['topology'] == 'V2'
    assert payload['algorithm'] == 'BASE'
    assert payload['experiment'] == f'V2_BASE_{plane}'
    provenance = payload['provenance']
    assert provenance['kind'] == 'history_recombine'
    assert provenance['source_plane'] == plane
    assert provenance['source_algorithm'] == {'z1': 'D', 'z2': 'C'}[plane]
    assert provenance['source_routes_sha256'] == sha256_file(
        SOURCE_ROUTES[plane])
    assert payload['algorithm_detail']['search_performed'] is False
    assert payload['algorithm_detail']['strategy']['search_performed'] is False
    config = load_json(plane_dir(plane) / 'config.json')
    assert config['experiment'] == f'V2_BASE_{plane}'
    assert config['plane'] == plane
    assert config['strategy']['name'] == 'history_recombine'
    assert config['strategy']['search_performed'] is False


# ---------------------------------------------------------------------------
# criterion 2: routed primitives are the historical ones, verbatim
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('plane', PLANES)
def test_plane_primitives_are_verbatim_history(plane):
    payload = plane_payload(plane)
    hist = load_json(SOURCE_ROUTES[plane])
    hist_by_id = {record['route_id']: record for record in hist['routes']}
    routed = [record for record in payload['routes']
              if record['status'] == 'routed']
    assert len(routed) == EXPECTED_ROUTED[plane]
    for record in routed:
        source = hist_by_id[record['route_id']]
        assert source['status'] == 'routed'
        assert record['primitives'] == source['primitives'], (
            f'{plane} route {record["route_id"]}: primitives changed')
        assert canonical_json(record['primitives']) == canonical_json(
            source['primitives'])
        assert record['length_mm'] == source['length_mm']
        assert record['bend_count'] == source['bend_count']
    # historical sources are read-only and unchanged since the acceptance run
    evidence = criterion(2)['evidence'][plane]
    assert evidence['source_routes_sha256'] == sha256_file(SOURCE_ROUTES[plane])


# ---------------------------------------------------------------------------
# criterion 3: authoritative strict audit
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('plane', PLANES)
def test_plane_strict_audit_passed(plane):
    audit = load_json(plane_dir(plane) / 'audit_strict.json')
    assert audit['passed'] is True
    assert audit['policy_used'] == 'strict'
    assert audit['policy'] == 'strict'
    assert audit['validator'] == 'four_side_1024.fslw.validate_fslw'
    assert audit['plane'] == plane
    assert audit['route_count'] == ROUTES_PER_PLANE
    assert audit['routed_count'] == EXPECTED_ROUTED[plane]
    assert audit['d56_passed_count'] == EXPECTED_ROUTED[plane]
    assert audit['d56_failed_count'] == 0
    assert audit['errors'] == []
    assert audit['violation_pair_count'] == 0
    for field in ('spacing_violation_pairs', 'overlap_pairs', 'touch_pairs',
                  'crossing_window_overlap_pairs', 'double_cross_pairs',
                  'crossing_window_excessive_pairs', 'self_intersections',
                  'self_overlaps', 'self_spacing_violations',
                  'radius_violations', 'boundary_violations',
                  'diagonal_line_violations', 'free_or_short_s_arc_violations'):
        assert audit[field] == 0, f'{plane}: {field} = {audit[field]}'
    assert audit['structure']['checked'] is True
    assert audit['routes_sha256'] == sha256_file(plane_dir(plane) / 'routes.json')
    assert audit['process']['radius_mm'] == 40.0
    assert audit['process']['centerline_clearance_mm'] == pytest.approx(0.08)
    expected_crossings = {'z1': 66775, 'z2': 7020}[plane]
    assert audit['crossing_count'] == expected_crossings


@pytest.mark.parametrize('plane', PLANES)
def test_plane_audit_schema_matches_historical_scan_output(plane):
    historical = HIST_ROOT / 'planes' / 'V2' / (
        'D' if plane == 'z1' else 'C') / plane / 'audit_strict.json'
    if not historical.exists():
        pytest.skip('historical audit file not available')
    historical_keys = set(load_json(historical))
    current_keys = set(load_json(plane_dir(plane) / 'audit_strict.json'))
    assert current_keys == historical_keys, (
        f'{plane}: audit_strict.json schema differs from the historical '
        f'scan_and_audit output: missing={sorted(historical_keys - current_keys)}, '
        f'extra={sorted(current_keys - historical_keys)}')


# ---------------------------------------------------------------------------
# criterion 4: statistics.json merged from the fresh audit
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('plane', PLANES)
def test_plane_statistics_audit_merged(plane):
    statistics = load_json(plane_dir(plane) / 'statistics.json')
    audit = load_json(plane_dir(plane) / 'audit_strict.json')
    assert statistics['audit_passed'] is True
    assert statistics['audit_policy'] == 'strict'
    assert statistics['total_violation_count'] == 0
    assert statistics['audit_violation_count'] == 0
    assert statistics['routed'] == EXPECTED_ROUTED[plane]
    assert statistics['connections_total'] == ROUTES_PER_PLANE
    assert statistics['routing_rate'] == EXPECTED_ROUTED[plane] / ROUTES_PER_PLANE
    assert statistics['crossing_count'] == audit['crossing_count']
    assert statistics['source']['audit']['status'] == 'merged'
    audit_file = statistics['source']['audit']['file']
    assert Path(audit_file).name == 'audit_strict.json'
    assert statistics['source']['audit_sha256'] == sha256_file(audit_file)
    assert statistics['source']['routes_sha256'] == sha256_file(
        plane_dir(plane) / 'routes.json')


# ---------------------------------------------------------------------------
# criterion 5: combined 1024-channel baseline
# ---------------------------------------------------------------------------
def test_combined_698_baseline():
    combined = OUT_ROOT / 'combined' / 'V2' / 'BASE'
    payload = load_json(combined / 'routes_1024.json')
    statistics = load_json(combined / 'statistics.json')
    summary = load_json(combined / 'planes_summary.json')
    records = payload['routes']
    assert len(records) == CONNECTIONS_TOTAL
    assert len({record['route_id'] for record in records}) == CONNECTIONS_TOTAL
    statuses = Counter(record['status'] for record in records)
    assert statuses['routed'] == EXPECTED_TOTAL_ROUTED
    assert statuses['failed'] == CONNECTIONS_TOTAL - EXPECTED_TOTAL_ROUTED
    by_plane = Counter(record['plane'] for record in records
                       if record['status'] == 'routed')
    assert dict(by_plane) == EXPECTED_ROUTED
    assert statistics['routed'] == EXPECTED_TOTAL_ROUTED
    assert statistics['unrouted'] == CONNECTIONS_TOTAL - EXPECTED_TOTAL_ROUTED
    assert statistics['connections_total'] == CONNECTIONS_TOTAL
    assert statistics['routing_rate'] == EXPECTED_TOTAL_ROUTED / CONNECTIONS_TOTAL
    assert statistics['by_plane']['z1']['routed'] == 492
    assert statistics['by_plane']['z2']['routed'] == 206
    assert statistics['audit_passed_all_planes'] is True
    assert statistics['violations']['complete'] is True
    assert statistics['violations']['same_plane_total'] == 0
    assert statistics['same_plane_crossings'] == 66775 + 7020
    # the combined payload points at the v01 plane payloads (provenance)
    for plane in PLANES:
        block = payload['plane_summaries'][plane]
        assert Path(block['routes_json']) == plane_dir(plane) / 'routes.json'
        assert block['routed'] == EXPECTED_ROUTED[plane]
        assert summary['planes'][plane]['routed'] == EXPECTED_ROUTED[plane]
    assert summary['combined']['routed'] == EXPECTED_TOTAL_ROUTED
    assert summary['combined']['routing_rate'] == (
        EXPECTED_TOTAL_ROUTED / CONNECTIONS_TOTAL)


def test_combined_two_height_gds_and_figures():
    gdspy = pytest.importorskip('gdspy')
    combined = OUT_ROOT / 'combined' / 'V2' / 'BASE'
    gds_path = combined / 'routing_1024_two_height.gds'
    assert gds_path.exists() and gds_path.stat().st_size > 0
    library = gdspy.GdsLibrary(infile=str(gds_path))
    tops = library.top_level()
    assert tops
    paths = list(tops[0].paths)
    layers = sorted({int(layer) for item in paths for layer in item.layers})
    datatypes = sorted({int(value) for item in paths for value in item.datatypes})
    layer_counts = {
        layer: sum(1 for item in paths
                   if any(int(value) == layer for value in item.layers))
        for layer in layers}
    # layer 0 = plane z1 (row 1, z=0.0); layer 1 = plane z2 (row 2, z=0.5)
    assert layers == [0, 1]
    assert datatypes == [0]
    assert layer_counts[0] == EXPECTED_ROUTED['z1']
    assert layer_counts[1] == EXPECTED_ROUTED['z2']
    for name in ('layer_2d.png', 'overlay_3d.png'):
        raw = (combined / name).read_bytes()[:8]
        assert raw == b'\x89PNG\r\n\x1a\n', f'{name} is not a PNG'
    svg = (combined / 'layer_2d.svg').read_text(encoding='utf-8',
                                                errors='replace')
    assert '<svg' in svg and '</svg>' in svg
    for plane in PLANES:
        assert (plane_dir(plane) / 'routing_all.gds').stat().st_size > 0
        assert (plane_dir(plane) / 'routing_all.svg').stat().st_size > 0


# ---------------------------------------------------------------------------
# criterion 6: independent recomputation spot checks
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('plane', PLANES)
def test_d56_leave_one_out_spot_check(plane):
    """Sample of the full D56Index leave-one-out self-check from the script."""
    payload = plane_payload(plane)
    routed = [record for record in payload['routes']
              if record['status'] == 'routed']
    index = d56_index.D56Index(width=fslw_config.WIDTH_MM,
                               gap=fslw_config.EDGE_GAP_MM,
                               crossing_policy='strict')
    prepared = {}
    for record in routed:
        prepared[record['route_id']] = d56_index.prepare(record['primitives'])
        index.add(record['route_id'], prepared[record['route_id']])
    sample = [routed[0]['route_id'], routed[len(routed) // 2]['route_id'],
              routed[-1]['route_id']]
    for route_id in sample:
        index.remove(route_id)
        evaluation = index.evaluate(prepared[route_id])
        index.add(route_id, prepared[route_id])
        assert evaluation.valid is True, (
            f'{plane} route {route_id}: {evaluation.reason} '
            f'blockers={evaluation.blockers[:5]}')


def test_crosscheck_agrees_on_sampled_pairs():
    """Router-index vs authoritative-validator verdicts must never disagree."""
    routes_path = plane_dir('z2') / 'routes.json'
    summary = crosscheck_fslw.crosscheck(routes_path, plane='z2', max_pairs=1500)
    assert summary['passed'] is True
    assert summary['mismatch_count'] == 0
    assert summary['validator_invalid_pairs'] == 0
    assert summary['router_invalid_pairs'] == 0
    assert summary['crossing_count']['matches'] is True


# ---------------------------------------------------------------------------
# criterion 7: historical comparison numbers
# ---------------------------------------------------------------------------
def test_historical_abcd_reference_table():
    evidence = criterion(7)['evidence']
    assert evidence['eight_group_count'] == 8
    assert evidence['v2_abcd_totals'] == {'A': 681, 'B': 677, 'C': 694,
                                          'D': 638}
    assert evidence['v2_reference_numbers_match'] is True
    assert evidence['best_historical_group'] == 'V2_C'
    assert evidence['best_historical_routed'] == 694
    assert evidence['baseline_698'] == EXPECTED_TOTAL_ROUTED
    assert evidence['delta_vs_best_historical'] == 4
    assert evidence['delta_vs_v2_default_B'] == 21
    assert evidence['problems'] == []
    table = {row['group']: row for row in evidence['comparison_table']}
    assert table['V2_C']['routed_total'] == 694
    assert table['V2_C']['z2_routed'] == 206
    assert table['V2_D']['routed_total'] == 638
    assert table['V2_D']['z1_routed'] == 492
    assert evidence['baseline_group'].startswith('V2_BASE')


def test_reproduce_readme_exists():
    readme = OUT_ROOT / 'baseline_reproduce.md'
    assert readme.exists()
    text = readme.read_text(encoding='utf-8')
    assert 'audit_baseline.py' in text
    assert 'four_side_1024\\v2opt\\tests' in text
    assert 'build_combined' in text
    assert '698/1024' in text
