"""Tests of the spatial grouped U-bundle 3D routing experiment.

Only cheap structural checks; the full geometric acceptance is the frozen
``l3d.validate_payload`` audit stored in the experiment's ``validation.json`` and
the independent verification report under ``verification/``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from four_side_1024.v3c4.profile import apply as apply_profile

apply_profile()

from four_side_1024.manual_c4 import spatial_u_bundle as S  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / \
    'outputs/manual_c4_new_connectivity/spatial_u_bundle_optimization'


@pytest.fixture(scope='module')
def campaign():
    return S.Campaign()


@pytest.fixture(scope='module')
def payloads():
    final = json.loads((OUT / 'routes_1024.json').read_text(encoding='utf-8'))
    u_only = json.loads((OUT / 'routes_1024_u_only.json').read_text(encoding='utf-8'))
    assignment = json.loads((OUT / 'u_layer_assignment.json').read_text(
        encoding='utf-8'))
    validation = json.loads((OUT / 'validation.json').read_text(encoding='utf-8'))
    summary = json.loads((OUT / 'summary.json').read_text(encoding='utf-8'))
    return dict(final=final, u_only=u_only, assignment=assignment,
                validation=validation, summary=summary)


def test_quartet_builder_geometry(campaign):
    routes, error = S.build_quartet(campaign, 20, 2, 1.0, 25.0, 11.2, 11.2)
    assert routes is not None, error
    assert len(routes) == 4
    for route in routes:
        assert route['layer_sequence'] == [1, 2, 1]
        assert route['n_transitions'] == 2
        kinds = [part['kind'] for part in route['parts']]
        assert kinds == ['flat', 'transition', 'flat', 'transition', 'flat']
        high = route['parts'][2]
        assert abs(high['z_mm'] - 1.0) <= 1e-9
        assert len(high['primitives']) == 5
        assert [p['kind'] for p in high['primitives']] == ['line', 'arc', 'line',
                                                           'arc', 'line']
        for primitive in high['primitives']:
            if primitive['kind'] == 'arc':
                assert abs(primitive['radius'] - 15.0) <= 1e-9
        # the transitions start exactly where the preceding flat part ends
        first = route['parts'][0]
        up = route['parts'][1]
        assert abs(first['z_mm'] - up['z0']) <= 1e-9
        assert abs(up['z1'] - high['z_mm']) <= 1e-9
        assert tuple(first['primitives'][-1]['p1']) == tuple(up['start'])
        # the high flat part starts exactly where the rise transition ends
        assert tuple(high['primitives'][0]['p0']) == tuple(up['end'])
        # 2D chain reconstruction is continuous
        chain = S.route_2d_primitives(route)
        assert chain[0]['kind'] == 'line'


def _assert_chains_close(first, second, tol=1e-6):
    assert len(first) == len(second)
    for one, other in zip(first, second):
        assert one['kind'] == other['kind']
        for field in ('p0', 'p1'):
            if field in one:
                assert len(one[field]) == len(other[field])
                for a, b in zip(one[field], other[field]):
                    assert abs(a - b) <= tol
        if one['kind'] == 'arc':
            for a, b in zip(one['center'], other['center']):
                assert abs(a - b) <= tol
            for field in ('radius', 'start_angle', 'sweep'):
                assert abs(one[field] - other[field]) <= tol


def test_quartet_is_exactly_c4_rotated(campaign):
    from four_side_1024.v3c4 import inputs as V3
    routes, error = S.build_quartet(campaign, 20, 2, 1.0, 25.0, 11.2, 11.2)
    assert routes is not None, error
    rep = S.route_2d_primitives(routes[0])
    for phase, route in enumerate(routes):
        chain = S.route_2d_primitives(route)
        if phase == 0:
            _assert_chains_close(rep, chain)
            continue
        rotated = V3.rotate_primitives(rep, phase)
        member = campaign.record(route['route_id'])
        oriented, _reversed = V3.orient_primitives(
            rotated, member['source_endpoint'], member['target_endpoint'])
        fake = {'parts': [dict(kind='flat', layer_id=1, z_mm=0.0,
                               length_mm=0.0, primitives=oriented)]}
        _assert_chains_close(S.route_2d_primitives(fake), chain)


def test_assignment_covers_all_target_quartets(payloads):
    assignment = payloads['assignment']
    assert assignment['target_quartets'] == 64
    assert assignment['reached'] == 64
    assert assignment['failed'] == 0
    rows = assignment['assignment']
    assert len(rows) == 64
    layers = {row['bundle']: set() for row in rows}
    for row in rows:
        assert row['status'] == 'target_layer_reached'
        assert row['entry_straight_mm'] is not None
        assert row['exit_straight_mm'] is not None
        assert row['rise_start_xy'] is not None
        assert row['fall_start_xy'] is not None
        layers[row['bundle']].add(row['target_layer'])
    assert layers == {'z1_middle_U': {2}, 'z2_corner_U_1': {2},
                      'z2_corner_U_2': {3}, 'z2_middle_U': {4}}
    moved = assignment['modified_non_u_routes']
    assert moved is not None and moved['group_id'] == 11
    assert moved['route_ids'] == [12, 231, 232, 29]
    assert moved['target_layer'] == 5


def test_final_payload_target_layers(payloads, campaign):
    records = {int(r['route_id']): r for r in payloads['final']['routes']}
    assert len(records) == 1024
    for gid in S.TARGET_GIDS:
        conf = S.BUNDLES[S.GID_BUNDLE[gid]]
        for rid in campaign.group_routes(gid):
            record = records[rid]
            assert record['status'] == 'routed'
            flats = [part for part in record['parts'] if part['kind'] == 'flat']
            assert any(abs(float(part['z_mm']) - conf['layer_z']) <= 1e-9
                       for part in flats), (gid, rid)
            assert record['layer_sequence'] == [1, conf['layer'], 1]
            assert record['n_transitions'] == 2


def test_non_target_routes_unchanged(payloads, campaign):
    baseline = {int(r['route_id']): r for r in campaign.baseline_payload['routes']}
    final = {int(r['route_id']): r for r in payloads['final']['routes']}
    u_only = {int(r['route_id']) for r in payloads['u_only']['routes']}
    moved = {12, 231, 232, 29}
    for rid, record in baseline.items():
        if rid in campaign.target_rids:
            continue
        if rid in moved:
            assert final[rid]['layer_sequence'] == [1, 5, 1]
            assert final[rid]['start_z_mm'] == record['start_z_mm']
            continue
        assert json.dumps(final[rid], sort_keys=True) == \
               json.dumps(record, sort_keys=True), rid
    assert len(u_only) == 1024


def test_validation_artifacts(payloads):
    validation = payloads['validation']
    for key in ('payload_validation', 'u_only_payload_validation',
                'baseline_payload_validation'):
        report = validation[key]
        assert report['exploratory_pass'] is True
        assert report['geometry_pass'] is True
        assert report['counts']['violations'] == 0
        assert report['counts']['clearance_violations'] == 0
        assert report['counts']['curvature_violations'] == 0
    summary = payloads['summary']
    assert summary['routed'] == 1024
    assert summary['target_quartets_reached'] == 64
    assert summary['same_layer_u_u_crossing_pairs'] == 0
    assert summary['unique_crossing_pairs'] < summary['baseline_pairs']
    assert Path(summary['figures']).is_dir()
