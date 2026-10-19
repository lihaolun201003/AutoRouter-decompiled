"""Contract tests for the ABCD scheduling strategies (no routing required)."""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import pytest

from four_side_1024 import inputs
from four_side_1024.abcd import strategies as S
from four_side_1024.d56.frames import build_frames
from four_side_1024.d56.search import build_order

DESKTOP = Path(r'C:\Users\lihao\Desktop')
V1 = DESKTOP / 'optical_1024_multitomulti_connectivity_v1.csv'
V2 = DESKTOP / 'optical_1024_multitomulti_connectivity_v2_symmetric.csv'


@pytest.fixture(scope='module')
def topology():
    path = V1 if V1.exists() else Path(__file__).resolve().parents[3] / \
        'data/optical_1024_multitomulti_connectivity_v1.csv'
    routes, endpoints, _connectors, _validation = inputs.load(path)
    frames = build_frames(routes, endpoints)
    return routes, frames


def test_algorithm_group_orders_match_the_frozen_task_definition():
    assert S.GROUP_ORDERS['A'] == ['NS', 'EW', 'EN', 'ES', 'SW', 'NW']
    assert S.GROUP_ORDERS['B'] == ['NW', 'EN', 'SW', 'ES', 'NS', 'EW']
    assert S.ALGORITHMS == ('A', 'B', 'C', 'D')


@pytest.mark.parametrize('algorithm', ['A', 'B'])
def test_sequential_orders_contain_every_identity_once(topology, algorithm):
    routes, frames = topology
    spec = S.sequential_strategy(algorithm)
    order = build_order(routes, frames, spec)
    assert len(order) == 1024
    assert len(set(order)) == 1024
    assert set(order) == {route['route_id'] for route in routes}


@pytest.mark.parametrize('direction', ['cw', 'ccw'])
@pytest.mark.parametrize('start_side', ['N', 'E', 'S', 'W'])
@pytest.mark.parametrize('batch', [1, 8, 32, 256])
def test_round_robin_never_duplicates_a_connection(topology, direction, start_side, batch):
    routes, frames = topology
    order = S.round_robin_order(routes, frames, start_side=start_side,
                               direction=direction, batch=batch)
    assert len(order) == 1024
    assert len(set(order)) == 1024
    assert set(order) == {route['route_id'] for route in routes}


def test_round_robin_sides_alternate_and_queues_are_mixed(topology):
    routes, frames = topology
    order = S.round_robin_order(routes, frames, start_side='N', direction='cw', batch=8)
    by_id = {route['route_id']: route for route in routes}
    # every side owns exactly 256 connections and each queue mixes both demands
    ownership = Counter(S.owner_side(route) for route in routes)
    assert ownership == {'N': 256, 'E': 256, 'S': 256, 'W': 256}
    for side in 'NESW':
        queue = [route for route in routes if S.owner_side(route) == side]
        relations = Counter('opposite' if route['pair'] in ('NS', 'EW') else 'adjacent'
                            for route in queue)
        assert relations['opposite'] == 128, (side, relations)
        assert relations['adjacent'] == 128, (side, relations)
    # the first `batch` scheduled routes come from the starting side, then rotate
    first_side = S.owner_side(by_id[order[0]])
    assert first_side == 'N'
    assert all(S.owner_side(by_id[route_id]) == 'N' for route_id in order[:8])
    assert all(S.owner_side(by_id[route_id]) == 'E' for route_id in order[8:16])
    # no connection is scheduled twice: the explicit order is a full partition
    assert len({route_id for route_id in order}) == 1024


def test_round_robin_order_is_deterministic(topology):
    routes, frames = topology
    first = S.round_robin_order(routes, frames, start_side='E', direction='ccw', batch=16)
    second = S.round_robin_order(routes, frames, start_side='E', direction='ccw', batch=16)
    assert first == second


def test_c_sweep_covers_all_required_dimensions():
    designs = S.C_SWEEP
    assert {item['direction'] for item in designs} == {'cw', 'ccw'}
    assert {item['start_side'] for item in designs} == {'N', 'E', 'S', 'W'}
    assert len({item['batch'] for item in designs}) >= 2
    assert len(designs) == 16
    assert all(item['batch'] > 0 for item in designs)
