"""Bounded regression checks for the two genuine cross-side legacy passes.

Scheduler tests mock expensive geometry/collision work deliberately; the
separate noCross fixture below executes the unchanged extracted rule bodies.
These tests do not claim a 1024-route physical routing result.
"""
from collections import Counter
import copy

import numpy as np
import pytest

from . import legacy_adapter as adapter
from .inputs import DEFAULT_INPUT, config, load
from .legacy_geometry import canonicalize
from .legacy_rules import LegacyRules, WGyset, nodesMTset


@pytest.fixture(scope='module')
def real_data():
    return load(DEFAULT_INPUT, config())


def _fast_geometry(monkeypatch):
    def straight_fixture(p, q, track, **kwargs):
        return [dict(kind='line', p0=list(map(float, p)),
                     p1=list(map(float, q)), layer=0)]
    monkeypatch.setattr(adapter, 'opposite', straight_fixture)
    monkeypatch.setattr(adapter, 'adjacent', straight_fixture)
    monkeypatch.setattr(adapter, 'validate', lambda *args, **kwargs: [])


def test_real_csv_assigns_512_routes_to_each_cross_side_pass(real_data):
    routes, _, _, _ = real_data
    counts = Counter(adapter.branch_for_source(r['source_side']) for r in routes)
    assert counts == {'above2below': 512, 'below2above': 512}
    assert {s: adapter.branch_for_source(s) for s in 'NSEW'} == {
        'N': 'above2below', 'S': 'below2above',
        'E': 'below2above', 'W': 'above2below'}
    with pytest.raises(ValueError):
        adapter.branch_for_source('X')


@pytest.mark.parametrize('branch', ['above2below', 'below2above'])
def test_track_scan_keeps_exact_direct_L_and_original_branch_direction(branch):
    qy = 42.123
    direct_y = 150. - qy if branch == 'above2below' else qy
    tracks = sorted([5., 5.175, 10., direct_y, 144.825])
    schedule = list(adapter.track_schedule('adjacent', qy, tracks, branch))
    i, rule_y, geometry_y, mode = schedule[0]
    assert mode == 'direct_L_interface'
    assert tracks[i] == pytest.approx(rule_y)
    assert rule_y == pytest.approx(direct_y)
    assert geometry_y == pytest.approx(qy)
    regular = schedule[1:]
    expected_indices = list(range(len(tracks)))
    if branch == 'below2above':
        expected_indices.reverse()
    assert [entry[0] for entry in regular] == expected_indices
    assert all(tracks[i] == rule_y for i, rule_y, _, _ in regular)
    for _, rule_y, geometry_y, _ in regular:
        assert geometry_y == pytest.approx(150. - rule_y if branch == 'above2below' else rule_y)


def test_outer_order_predicates_preserve_original_strictness_and_source_rule():
    track = WGyset(y=20., rEnd=[-1, 3], lEnd=[100, 1], WGs=[99])
    # above2below permits a repeated source connector; below2above does not.
    assert adapter.legacy_order_ok('above2below', 20., 3, 4, track)
    assert not adapter.legacy_order_ok('below2above', 20., 3, 4, track)
    # Target equality is allowed only in below2above.
    assert not adapter.legacy_order_ok('above2below', 20., 2, 3, track)
    assert adapter.legacy_order_ok('below2above', 20., 2, 3, track)
    assert not adapter.legacy_order_ok('above2below', 4.99, 2, 4, track)
    assert not adapter.legacy_order_ok('below2above', 145., 2, 4, track)
    with pytest.raises(ValueError):
        adapter.legacy_order_ok('not_a_pass', 20., 2, 4, track)


@pytest.mark.parametrize('previous_r,previous_l,expected_above,expected_below', [
    (0, 0, False, True),
    (2, 1, True, False),
])
def test_unchanged_noCross_bodies_make_distinct_branch_decisions(
        previous_r, previous_l, expected_above, expected_below):
    xs = [[10. * j + .175 * i for i in range(32)] for j in range(3)]
    rules = LegacyRules(nodesMTset(xs, xs), lambda lx, ly: 4)
    tracks = [WGyset(y=5. + i * .175, rEnd=[-1], lEnd=[100]) for i in range(12)]
    tracks[5].WGs.append(99)
    tracks[5].rEnd.append(previous_r)
    tracks[5].lEnd.append(previous_l)
    args = (1, 2, 6, tracks)
    assert rules.noCross(*args, _type='above2below', lx=20., ly=0.) is expected_above
    assert rules.noCross(*args, _type='below2above', lx=20., ly=0.) is expected_below


def test_old_256_config_does_not_cut_off_one_route_before_global_budget(monkeypatch, real_data):
    routes, endpoints, _, _ = real_data
    _fast_geometry(monkeypatch)

    class PermissiveRules:
        def __init__(self, *args, **kwargs):
            pass

        def noCross(self, *args, **kwargs):
            return True

    class RejectEveryCandidate:
        calls = 0

        def __init__(self, **kwargs):
            pass

        def evaluate(self, primitives):
            type(self).calls += 1
            return dict(valid=False, spacing_pairs=[999])

        def add(self, *args):
            pytest.fail('Rejected candidates must not be committed')

    monkeypatch.setattr(adapter, 'LegacyRules', PermissiveRules)
    monkeypatch.setattr(adapter, 'ConflictIndex', RejectEveryCandidate)
    cfg = config()
    cfg.update(search_seconds=60., candidate_evaluation_budget=300,
               max_track_evaluations_per_route=256)
    accepted, failed, search = adapter.route_original(routes, endpoints, cfg, lambda message: None)
    assert not accepted and len(failed) == 1024
    assert RejectEveryCandidate.calls == search['candidate_evaluations'] == 300
    assert max(record['evaluated'] for record in failed.values()) == 300
    assert sum(record['evaluated'] for record in failed.values()) == 300
    assert search['per_route_evaluation_limit'] is None
    assert {record['reason'] for record in failed.values()} == {'search_budget_exhausted'}
    assert all('per_route_track_budget_exhausted' not in record['rejection_counts']
               for record in failed.values())


def test_both_route_passes_use_real_role_coordinates_and_commit_rule_frame_state(monkeypatch, real_data):
    routes, endpoints, _, _ = real_data
    routes_before, endpoints_before = copy.deepcopy(routes), copy.deepcopy(endpoints)
    _fast_geometry(monkeypatch)
    contexts = []
    instances = []
    calls = Counter()
    expected_by_pair = {}
    for pair in adapter.GROUP_ORDER:
        route = next(r for r in routes if r['pair'] == pair)
        source_side, target_side = route['source_side'], route['target_side']
        _, _, transform, kind = canonicalize(source_side, target_side,
            endpoints[route['source_endpoint']]['routing_xy'],
            endpoints[route['target_endpoint']]['routing_xy'])
        matrix, offset = np.asarray(transform['matrix']), np.asarray(transform['offset'])
        target_axis = 0 if kind == 'opposite' else 1

        def coordinate(e):
            return matrix @ np.asarray(e['routing_xy']) + offset

        role_coordinates = []
        for side, axis in ((source_side, 0), (target_side, target_axis)):
            connector_names = {e['connector'] for e in endpoints.values() if e['side'] == side}
            connector_coordinates = {
                name: sorted(float(coordinate(e)[axis]) for e in endpoints.values()
                             if e['connector'] == name) for name in connector_names}
            names = sorted(connector_names, key=lambda name: np.mean(connector_coordinates[name]))
            role_coordinates.append((names, [connector_coordinates[name] for name in names]))
        expected_by_pair[pair] = (transform, target_axis, role_coordinates)

    class ContextSpyRules:
        def __init__(self, nodes, callback, **kwargs):
            pair = adapter.GROUP_ORDER[len(contexts)]
            route = next(r for r in routes if r['pair'] == pair)
            branch = adapter.branch_for_source(route['source_side'])
            _, _, (source, target) = expected_by_pair[pair]
            self.nodes, self.callback, self.branch = nodes, callback, branch
            assert [mt.x for mt in nodes.MTabove] == (source[1] if branch == 'above2below' else target[1])
            assert [mt.x for mt in nodes.MTbelow] == (target[1] if branch == 'above2below' else source[1])
            assert all(mt.y == [0.] * 32 for mt in nodes.MTabove)
            assert all(mt.y == [150.] * 32 for mt in nodes.MTbelow)
            contexts.append((pair, self))

        def noCross(self, lEnd, rEnd, i, tracks, *, _type, lx, ly):
            assert _type == self.branch
            # Above pass uses target/below channel; below pass source/below.
            connector = self.nodes.MTbelow[lEnd if _type == 'above2below' else rEnd]
            ordinal = connector.x.index(lx)
            assert self.callback(lx, ly) == max(ordinal - 6, 4)
            assert ly == 0.
            self.last_rule_track = tracks[i].y
            calls[_type] += 1
            return True

    class AcceptEveryCandidate:
        def __init__(self, **kwargs):
            self.committed = {}
            instances.append(self)

        def evaluate(self, primitives):
            return dict(valid=True)

        def add(self, route_id, primitives):
            self.committed[route_id] = primitives

    def checked_geometry(p, q, track, **kwargs):
        rules = contexts[-1][1]
        assert rules.last_rule_track == pytest.approx(
            150. - track if rules.branch == 'above2below' else track)
        return [dict(kind='line', p0=list(map(float, p)),
                     p1=list(map(float, q)), layer=0)]

    monkeypatch.setattr(adapter, 'LegacyRules', ContextSpyRules)
    monkeypatch.setattr(adapter, 'ConflictIndex', AcceptEveryCandidate)
    monkeypatch.setattr(adapter, 'opposite', checked_geometry)
    monkeypatch.setattr(adapter, 'adjacent', checked_geometry)
    cfg = config()
    cfg.update(search_seconds=60., candidate_evaluation_budget=2000)
    accepted, failed, search = adapter.route_original(routes, endpoints, cfg, lambda message: None)
    assert len(accepted) == 1024 and not failed
    assert calls == search['branch_calls'] == {'above2below': 512, 'below2above': 512}
    assert len(instances) == 1 and set(instances[0].committed) == set(range(1, 1025))
    contexts_by_pair = dict(contexts)
    for route in routes:
        record = accepted[route['route_id']]
        assert record['source_endpoint'] == route['source_endpoint']
        assert record['target_endpoint'] == route['target_endpoint']
        assert record['layer'] == 0
        assert all(primitive['layer'] == 0 for primitive in record['primitives'])
        branch = adapter.branch_for_source(route['source_side'])
        assert record['legacy_pass'] == branch
        assert record['rule_track_mm'] == pytest.approx(
            150. - record['track_mm'] if branch == 'above2below' else record['track_mm'])
        transform, target_axis, (source, target) = expected_by_pair[route['pair']]
        p, q, _, _ = canonicalize(route['source_side'], route['target_side'],
            endpoints[route['source_endpoint']]['routing_xy'],
            endpoints[route['target_endpoint']]['routing_xy'])
        nodes = contexts_by_pair[route['pair']].nodes
        for role, coordinates, values, mts in (
            ('source', source, p, nodes.MTabove if branch == 'above2below' else nodes.MTbelow),
            ('target', target, q, nodes.MTbelow if branch == 'above2below' else nodes.MTabove),
        ):
            axis = 0 if role == 'source' else target_axis
            connector_index = coordinates[0].index(endpoints[route[role + '_endpoint']]['connector'])
            channel_index = mts[connector_index].x.index(float(values[axis]))
            assert mts[connector_index].y[channel_index] == record['rule_track_mm']
    assert routes == routes_before and endpoints == endpoints_before
