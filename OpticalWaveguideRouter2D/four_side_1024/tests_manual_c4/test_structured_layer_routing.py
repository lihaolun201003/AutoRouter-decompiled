"""Tests of the structured layer routing experiment (groups A and B)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from four_side_1024.v3c4.profile import apply as apply_profile

apply_profile()

from four_side_1024.manual_c4 import structured_layer_routing as S  # noqa: E402
from four_side_1024.v3c4 import inputs as V3  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / \
    'outputs/manual_c4_new_connectivity/structured_layer_routing'


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _group_data(group):
    root = OUT / group
    payload = _read(root / 'routes_1024.json')
    summary = _read(root / 'summary.json')
    validation = _read(root / 'validation.json')
    u_doc = _read(root / 'u_layer_assignment.json')
    opposite_doc = _read(root / 'opposite_assignment.json')
    return dict(root=root, payload=payload, summary=summary,
                validation=validation, u=u_doc, opposite=opposite_doc,
                campaign=S.StructuredCampaign(swap_rows=(group == 'B')))


@pytest.fixture(scope='module', params=['A', 'B'])
def data(request):
    return _group_data(request.param)


def test_payload_identity_and_ports(data):
    campaign = data['campaign']
    payload = data['payload']
    records = {int(record['route_id']): record
               for record in payload['routes'] if record.get('status') == 'routed'}
    assert len(records) == 1024
    ports = []
    for rid, record in campaign.manifest.items():
        got = records[rid]
        for key in ('plane', 'source_endpoint', 'target_endpoint',
                    'source_row', 'target_row', 'relation', 'pair'):
            assert got[key] == record[key], (rid, key)
        ports.append(got['source_endpoint'])
        ports.append(got['target_endpoint'])
    assert len(ports) == 2048
    assert len(set(ports)) == 2048


def test_rule_layers(data):
    campaign = data['campaign']
    payload = data['payload']
    records = {int(record['route_id']): record
               for record in payload['routes'] if record.get('status') == 'routed'}
    for rid in campaign.flat_rids:
        record = records[rid]
        assert record['layer_sequence'] == [1]
        assert record['n_transitions'] == 0
        assert abs(float(record['start_z_mm']) - campaign.base_z(rid)) <= 1e-9
    opposite_l2 = set()
    for gid in data['opposite']['groups']:
        if gid['status'] == 'L2':
            for rid in gid['route_ids']:
                opposite_l2.add(int(rid))
    for rid in campaign.opposite_rids:
        record = records[rid]
        if rid in opposite_l2:
            assert record['layer_sequence'] == [1, 2, 1]
            flats = [part for part in record['parts'] if part['kind'] == 'flat']
            assert any(abs(float(part['z_mm']) - 1.0) <= 1e-9 for part in flats)
        else:
            assert record['layer_sequence'] == [1]
    for gid in data['u']['groups']:
        for rid in gid['route_ids']:
            record = records[rid]
            if gid['status'] == 'target_layer_reached':
                assert record['layer_sequence'] == [1, gid['target_layer'], 1]
                flats = [part for part in record['parts'] if part['kind'] == 'flat']
                assert any(abs(float(part['z_mm']) - gid['target_z_mm']) <= 1e-9
                           for part in flats)
            else:
                # documented failure: kept flat on the interface plane
                assert gid.get('failure')
                assert record['layer_sequence'] == [1]
                assert record['n_transitions'] == 0


def test_assignments_consistent_with_summary(data):
    summary = data['summary']
    u = data['u']
    opposite = data['opposite']
    assert u['total_groups'] == 64
    assert u['target_reached_groups'] == summary['u_target_reached_groups']
    assert u['failed_groups'] == summary['u_failed_groups']
    assert len(u['groups']) == 64
    assert opposite['total_groups'] == 68
    assert opposite['l2_groups'] == summary['opposite_l2_groups']
    assert opposite['exception_groups'] == summary['opposite_exception_groups']
    assert summary['routed'] == 1024
    if data['campaign'].swap_rows:
        assert summary['same_layer_u_u_crossing_pairs'] >= 0
    else:
        assert summary['same_layer_u_u_crossing_pairs'] == 0
    layers = summary['layer_counts']
    assert layers['L1-z1']['count'] == 512
    assert layers['L1-z2']['count'] == 512
    assert layers['L2']['count'] == summary['opposite_l2_routes']
    raised = layers['L2']['count'] + layers['L3']['count'] + \
        layers['L4']['count'] + layers['L5']['count']
    assert raised == summary['opposite_l2_routes'] + \
        4 * summary['u_target_reached_groups']


def test_authoritative_validation(data):
    report = data['validation']['payload_validation']
    assert report['exploratory_pass'] is True
    assert report['geometry_pass'] is True
    assert report['counts']['violations'] == 0
    for key in ('clearance_violations', 'same_plane_violations',
                'curvature_violations', 'geometry_errors', 'contract_errors',
                'port_errors'):
        assert report['counts'][key] == 0
    stats = report.get('stats') or {}
    clearance = stats.get('min_3d_clearance_mm')
    assert clearance is not None and clearance >= 0.08 - 1e-9


def test_figures_delivered(data):
    root = data['root']
    figures = sorted((root / 'figures').glob('*.png'))
    assert len(figures) == 15, [path.name for path in figures]
    assert (root / 'ARTEFACTS_READY').exists()
    for name in ('routes_1024.json', 'summary.json', 'validation.json',
                 'u_layer_assignment.json', 'opposite_assignment.json'):
        assert (root / name).exists()


def test_c4_group_geometry_sample():
    campaign = S.StructuredCampaign(swap_rows=False)
    for gid in (20, 144, 160, 176, 1, 144):
        ids = campaign.group_routes(gid)
        rep_prims = campaign.primitives_2d(ids[0])
        for phase, rid in enumerate(ids):
            if phase == 0:
                continue
            rotated = V3.rotate_primitives(rep_prims, phase)
            member = campaign.record(rid)
            oriented, _reversed = V3.orient_primitives(
                rotated, member['source_endpoint'], member['target_endpoint'])
            got = campaign.primitives_2d(rid)
            assert len(oriented) == len(got)
            for one, other in zip(oriented, got):
                assert one['kind'] == other['kind']
                if one['kind'] == 'arc':
                    assert abs(one['radius'] - other['radius']) <= 1e-6

