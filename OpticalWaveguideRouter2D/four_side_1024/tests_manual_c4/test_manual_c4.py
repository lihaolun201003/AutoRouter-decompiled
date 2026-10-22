"""Tests of the new manual C4 connectivity adapter and 2D group router.

The physical acceptance of the produced routes is covered by the frozen
``four_side_1024.fslw.validate_fslw`` audit in the runners; these tests only pin the
adapter's data contract so that a future edit cannot silently change the topology,
the C4 grouping or the same-side U candidate family.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from four_side_1024.v3c4.profile import apply as apply_profile

apply_profile()

from four_side_1024.manual_c4 import connectivity as CONN  # noqa: E402
from four_side_1024.manual_c4.router import (  # noqa: E402
    BULGE_LADDER, ManualGroupRouter)
from four_side_1024.manual_c4.state import state_for  # noqa: E402


@pytest.fixture(scope='module')
def topology():
    if not CONN.COMBINED_JSON.exists():
        CONN.build_topology()
    return CONN.combined_topology()


def test_combined_topology_identity(topology):
    assert topology['connections'] == 1024
    assert topology['group_count'] == 256
    assert topology['relation_counts'] == {'opposite': 272, 'same': 256,
                                           'adjacent': 496}
    assert topology['group_kinds'] == {'opposite': 68, 'same': 64, 'adjacent': 124}
    assert topology['rotation_closure'] == {'90deg': 0, '180deg': 0, '270deg': 0}
    routes = topology['routes']
    assert [route['route_id'] for route in routes] == list(range(1, 1025))
    assert sum(1 for r in routes if r['plane'] == 'z1') == 512
    assert sum(1 for r in routes if r['plane'] == 'z2') == 512


def test_groups_are_strict_c4_orbits(topology):
    groups = topology['groups']
    assert len(groups) == 256
    assert Counter(group['plane'] for group in groups) == {'z1': 128, 'z2': 128}
    seen = set()
    for group in groups:
        assert len(group['route_ids']) == 4
        assert len(set(group['route_ids'])) == 4
        seen.update(group['route_ids'])
    assert len(seen) == 1024
    # every group is closed under the 90 deg port rotation (coordinate based)
    endpoints = CONN.endpoints()
    by_id = {route['route_id']: route for route in topology['routes']}
    rot = {eid: CONN.rot90_port(eid) for eid in endpoints}
    for group in groups:
        for route_id in group['route_ids']:
            route = by_id[route_id]
            rotated = frozenset(rot[eid] for eid in
                                (route['source_endpoint'], route['target_endpoint']))
            match = [rid for rid in group['route_ids']
                     if frozenset((by_id[rid]['source_endpoint'],
                                   by_id[rid]['target_endpoint'])) == rotated]
            assert len(match) == 1


def test_plane_port_usage(topology):
    endpoints = CONN.endpoints()
    for plane in ('z1', 'z2'):
        routes = CONN.load_plane(plane)[0]
        usage = Counter()
        for route in routes:
            usage[route['source_endpoint']] += 1
            usage[route['target_endpoint']] += 1
        expected = {eid for eid, ep in endpoints.items() if ep['plane'] == plane}
        assert set(usage) == expected
        assert set(usage.values()) == {1}
        assert all(route['source_row'] == route['target_row'] for route in routes)


def test_same_side_feasibility_at_r15():
    from four_side_1024.fslw import config as C
    separations = []
    for plane in ('z1', 'z2'):
        for route in CONN.load_plane(plane)[0]:
            if route['relation'] != 'same':
                continue
            endpoints = CONN.endpoints()
            ax, ay = endpoints[route['source_endpoint']]['routing_xy']
            bx, by = endpoints[route['target_endpoint']]['routing_xy']
            separations.append(abs(ax - bx) if route['source_side'] in 'NS'
                               else abs(ay - by))
    assert separations
    assert min(separations) >= 2.0 * float(C.RADIUS_MM) - 1e-9
    assert BULGE_LADDER[0] == 0.0 and len(BULGE_LADDER) >= 60


def test_group_router_smoke_one_group_per_kind():
    for plane, kinds in (('z1', ('opposite', 'adjacent', 'same')),
                         ('z2', ('opposite', 'adjacent', 'same'))):
        groups = CONN.groups_for_plane(plane)
        for kind in kinds:
            state = state_for(plane, log=lambda *a, **k: None)
            router = ManualGroupRouter(state, groups, log=lambda *a, **k: None)
            cache = router.prime_same_candidates()
            group = next(group for group in groups if group['kind'] == kind)
            results, failure, stats = router.attempt_group(
                group, budget=200,
                same_candidates=cache.get(group['group_id']))
            assert results is not None, (plane, kind, failure)
            assert len(results) == 4
            for result in results:
                assert result.prepared.length > 0


def test_modified_runners_keep_historical_defaults():
    import inspect

    from four_side_1024.v3c4 import ablation, dynamic_run

    assert inspect.signature(ablation.run_full).parameters['v4_root'].default is None
    assert inspect.signature(ablation.build_comparison).parameters['label'].default \
        == 'V4-C4'
    assert inspect.signature(dynamic_run.run).parameters['v4_root'].default is None
    assert inspect.signature(dynamic_run.run).parameters['label'].default == 'V4-C4'
