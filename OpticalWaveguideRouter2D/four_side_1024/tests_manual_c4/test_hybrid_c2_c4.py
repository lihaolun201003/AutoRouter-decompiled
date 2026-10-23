"""Tests for the hybrid C2/C4 directional layer routing experiment (H/V)."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from four_side_1024.v3c4.profile import apply as apply_profile

apply_profile()

from four_side_1024.manual_c4 import hybrid_c2_c4 as HC  # noqa: E402
from four_side_1024.v3c4 import inputs as V3  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / \
    'outputs/manual_c4_new_connectivity/hybrid_c2_c4_directional'
A_DIR = Path(__file__).resolve().parents[2] / \
    'outputs/manual_c4_new_connectivity/structured_layer_routing/A'


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def data():
    dataset = HC.HybridData()
    result = {}
    for variant in ('H', 'V'):
        root = OUT / variant
        result[variant] = dict(
            root=root,
            payload=_read(root / 'routes_1024.json'),
            summary=_read(root / 'summary.json'),
            validation=_read(root / 'validation.json'),
            assignment=_read(root / 'c2_pair_assignment.json'),
            analysis=_read(root / 'crossing_analysis.json'))
    a_payload = _read(A_DIR / 'routes_1024.json')
    return dict(hybrid=dataset, result=result,
                a_records={int(r['route_id']): r for r in a_payload['routes']})


def test_identity_and_ports(data):
    dataset = data['hybrid']
    for variant in ('H', 'V'):
        payload = data['result'][variant]['payload']
        records = {int(r['route_id']): r for r in payload['routes']
                   if r.get('status') == 'routed'}
        assert len(records) == 1024
        ports = []
        for rid, record in dataset.manifest.items():
            got = records[rid]
            for key in ('plane', 'source_endpoint', 'target_endpoint',
                        'source_row', 'target_row', 'relation', 'pair'):
                assert got[key] == record[key], (variant, rid, key)
            ports.append(got['source_endpoint'])
            ports.append(got['target_endpoint'])
        assert len(set(ports)) == 2048


def test_direction_rule_layers(data):
    dataset = data['hybrid']
    for variant in ('H', 'V'):
        payload = data['result'][variant]['payload']
        records = {int(r['route_id']): r for r in payload['routes']
                   if r.get('status') == 'routed'}
        assignment = data['result'][variant]['assignment']
        lift_dir = 'EW' if variant == 'H' else 'NS'
        keep_dir = 'NS' if variant == 'H' else 'EW'
        lifted = 0
        for row in assignment['pairs']:
            rid = int(row['route_ids'][0])
            record = records[rid]
            if row['status'] == 'lifted_L2':
                lifted += 1
                assert record['layer_sequence'] == [1, 2, 1]
                assert HC.direction_of(dataset.manifest, rid) == lift_dir
                flats = [p for p in record['parts'] if p['kind'] == 'flat']
                assert any(abs(float(p['z_mm']) - 1.0) <= 1e-9 for p in flats)
            else:
                assert row['failure']
                assert record['layer_sequence'] == [1]
                assert record['n_transitions'] == 0
                assert HC.direction_of(dataset.manifest, rid) == lift_dir
        assert lifted == 64
        # the kept direction must be flat on L1-z1 for all its routes
        for rid in dataset.z1_opposite:
            if HC.direction_of(dataset.manifest, rid) == keep_dir:
                assert records[rid]['layer_sequence'] == [1]


def test_fixed_c4_parts_unchanged(data):
    dataset = data['hybrid']
    a_records = data['a_records']
    fixed_rids = set(dataset.u_rids) | set(dataset.z2_opposite) | \
        {rid for rid in dataset.manifest
         if dataset.manifest[rid]['relation'] == 'adjacent'}
    for variant in ('H', 'V'):
        payload = data['result'][variant]['payload']
        records = {int(r['route_id']): r for r in payload['routes']}
        for rid in fixed_rids:
            assert json.dumps(records[rid], sort_keys=True) == \
                json.dumps(a_records[rid], sort_keys=True), (variant, rid)


def test_validation_counts_zero(data):
    for variant in ('H', 'V'):
        report = data['result'][variant]['validation']['payload_validation']
        assert report['exploratory_pass'] is True
        assert report['geometry_pass'] is True
        for key, value in report['counts'].items():
            assert value == 0, (variant, key)
        stats = report.get('stats') or {}
        clearance = stats.get('min_3d_clearance_mm')
        assert clearance is not None and clearance >= 0.08 - 1e-9


def test_crossing_metrics(data):
    dataset = data['hybrid']
    # A baseline recomputed by the same audit
    a_records = list(data['a_records'].values())
    audit_a, unique_a = HC.audit_height(a_records, dataset.manifest, dataset)
    assert unique_a == 19584
    assert audit_a['0.0']['pairs'] == 17576
    hv_a = 0
    for height, info in audit_a.items():
        for key, value in info['breakdown'].items():
            parts = key.split(' x ')
            if all(part.startswith('opposite_z1') for part in parts):
                dirs = {part.rsplit('_', 1)[1] for part in parts}
                if dirs == {'EW', 'NS'}:
                    hv_a += value
    assert hv_a == 10928
    for variant in ('H', 'V'):
        summary = data['result'][variant]['summary']
        analysis = data['result'][variant]['analysis']
        assert summary['routed'] == 1024
        assert summary['unique_crossing_pairs'] == 12960
        assert summary['z1_hv_same_height_pairs'] == 7032
        assert summary['crossing_pairs_by_height']['0.0'] == 11952
        assert summary['crossing_pairs_by_height']['1.0'] == 0
        assert analysis['reduction']['z1_hv_same_height_reduction'] == 3896
        assert analysis['reduction']['global_reduction'] == 6624


def _chains_close(one, other, tol=1e-6):
    if len(one) != len(other):
        return False
    for a, b in zip(one, other):
        if a['kind'] != b['kind']:
            return False
        for field in ('p0', 'p1'):
            if field in a:
                for x, y in zip(a[field], b[field]):
                    if abs(x - y) > tol:
                        return False
        if a['kind'] == 'arc':
            for x, y in zip(a['center'], b['center']):
                if abs(x - y) > tol:
                    return False
            for field in ('radius', 'start_angle', 'sweep'):
                if abs(a[field] - b[field]) > tol:
                    return False
    return True


def test_c2_c4_symmetry_samples(data):
    dataset = data['hybrid']
    campaign = dataset.campaign
    checked_pairs = 0
    for variant in ('H', 'V'):
        assignment = data['result'][variant]['assignment']
        for row in assignment['pairs']:
            if row['status'] != 'lifted_L2':
                continue
            first, second = int(row['route_ids'][0]), int(row['route_ids'][1])
            prims = campaign.primitives_2d(first)
            partner = campaign.primitives_2d(second)
            member = campaign.record(second)
            rotated = V3.rotate_primitives(prims, 2)
            oriented, _ = V3.orient_primitives(
                rotated, member['source_endpoint'], member['target_endpoint'])
            assert _chains_close(oriented, partner), (variant, first, second)
            checked_pairs += 1
    assert checked_pairs == 128
    # z2 U C4 sample
    for gid in (160, 176):
        ids = campaign.group_routes(gid)
        rep = campaign.primitives_2d(ids[0])
        for phase, rid in enumerate(ids[1:], start=1):
            member = campaign.record(rid)
            rotated = V3.rotate_primitives(rep, phase)
            oriented, _ = V3.orient_primitives(
                rotated, member['source_endpoint'], member['target_endpoint'])
            got = campaign.primitives_2d(rid)
            assert _chains_close(oriented, got), (gid, phase, rid)


def test_artefacts(data):
    for variant in ('H', 'V'):
        root = data['result'][variant]['root']
        for name in ('routes_1024.json', 'c2_pair_assignment.json',
                     'crossing_analysis.json', 'validation.json', 'summary.json',
                     'READY', 'ARTEFACTS_READY'):
            assert (root / name).exists(), (variant, name)
        assert len(list((root / 'figures').glob('*.png'))) == 13
        assignment = data['result'][variant]['assignment']
        assert assignment['total_pairs'] == 66
        assert assignment['lifted_pairs'] + assignment['failed_pairs'] == 66
