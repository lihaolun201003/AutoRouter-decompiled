"""V3 core regression tests (input adapter, frames, same-side geometry, strategies).

These tests do NOT need any output artifact: they operate on the frozen inputs and the
geometry builders, so they guard the core while the 8 official runs are produced.
"""
from __future__ import annotations

import math

import pytest

from four_side_1024.v3 import config as C
from four_side_1024.v3 import frames as vframes
from four_side_1024.v3 import geom_same, inputs, ports, strategies

PLANES = ('z1', 'z2')


@pytest.fixture(scope='module')
def loaded():
    connections, validation = inputs.load_all()
    return connections, validation


def test_topology_contract(loaded):
    connections, validation = loaded
    assert validation['passed'], validation['issues']
    assert validation['relation_counts'] == C.EXPECTED['relation_counts']
    assert validation['pair_counts'] == C.EXPECTED['pair_counts']
    assert validation['csv_sha256_match']
    assert validation['excel']['passed'], validation['excel']['issues']


def test_plane_split_and_relations(loaded):
    connections, _validation = loaded
    for plane, expected in C.EXPECTED['planes'].items():
        routes, endpoints, _connectors, validation = ports.load_plane(plane)
        assert validation['passed'], validation['issues']
        assert len(routes) == 512
        assert len(endpoints) == 1024
        assert validation['relations'] == {
            'same': expected['same'], 'opposite': expected['opposite'],
            'adjacent': expected['adjacent']}
        assert sum(1 for route in routes if route['relation'] == 'same') > 0
        assert sum(1 for route in routes if route['relation'] == 'opposite') > 0
        assert sum(1 for route in routes if route['relation'] == 'adjacent') > 0


def test_same_side_frames_are_rigid_rotations():
    for side in 'NESW':
        transform = vframes.SAME_TRANSFORMS[side]
        matrix = transform['matrix']
        determinant = matrix[0][0] * matrix[1][1] - matrix[0][1] * matrix[1][0]
        assert abs(abs(determinant) - 1.0) < 1e-12
        # the shared edge maps to y = 0 and the inward direction to +y
        example = {'N': (30.0, 150.0), 'S': (30.0, 0.0),
                   'E': (150.0, 30.0), 'W': (0.0, 30.0)}[side]
        # shift along the shared edge (x for N/S, y for E/W) so both stay on the edge
        shift = (1.0, 0.0) if side in 'NS' else (0.0, 1.0)
        p, q, _transform, kind = vframes.canonicalize_same(
            side, example, (example[0] + shift[0], example[1] + shift[1]))
        assert kind == 'same'
        assert abs(p[1]) < 1e-9 and abs(q[1]) < 1e-9
        inward = {'N': (0.0, -1.0), 'S': (0.0, 1.0),
                  'E': (-1.0, 0.0), 'W': (1.0, 0.0)}[side]
        mapped = (matrix[0][0] * inward[0] + matrix[0][1] * inward[1],
                  matrix[1][0] * inward[0] + matrix[1][1] * inward[1])
        assert abs(mapped[0]) < 1e-9 and abs(mapped[1] - 1.0) < 1e-9


def test_frames_keep_endpoint_identity(loaded):
    _connections, _validation = loaded
    routes, endpoints, _connectors, _validation = ports.load_plane('z1')
    frame_map = vframes.build_frames(routes, endpoints)
    assert len(frame_map) == 512
    for route in routes[:50]:
        frame = frame_map[route['route_id']]
        assert frame.src_xy == pytest.approx(
            tuple(endpoints[route['source_endpoint']]['routing_xy']))
        assert frame.dst_xy == pytest.approx(
            tuple(endpoints[route['target_endpoint']]['routing_xy']))
        assert frame.relation == route['relation']


def test_same_side_u_and_hairpins_are_legal_quarter_arcs():
    p, q = (20.0, 0.0), (110.0, 0.0)
    u = geom_same.same_u(p, q, 60.0)
    assert u is not None
    hairpin = geom_same.same_hairpin_a((60.0, 0.0), (100.0, 0.0), 0.0, 1.0)
    if hairpin is None:
        hairpin = geom_same.same_hairpin_b((60.0, 0.0), (100.0, 0.0), None, 1.0)
    assert hairpin is not None
    for primitives in (u, hairpin):
        for primitive in primitives:
            if primitive['kind'] == 'arc':
                # quarter arcs (U corners / hairpin) or short-S arcs (theta <= 90 deg)
                assert abs(primitive['radius'] - C.RADIUS_MM) < 1e-9
                assert abs(primitive['sweep']) <= math.pi / 2 + 1e-6
            else:
                p0, p1 = primitive['p0'], primitive['p1']
                assert abs(p0[0] - p1[0]) < 1e-9 or abs(p0[1] - p1[1]) < 1e-9


def test_same_side_hairpin_covers_small_separation():
    # nearly all real same-side pairs have |dx| < 2R; the hairpin family must serve them
    dx_values = [1.0, 5.0, 20.0, 39.9, 55.0, 79.0]
    for dx in dx_values:
        p = (40.0, 0.0)
        q = (40.0 + dx, 0.0)
        primitives = geom_same.same_hairpin_a(p, q, 0.0, 1.0)
        if primitives is None:
            primitives = geom_same.same_hairpin_b(p, q, None, 1.0)
        assert primitives is not None, dx


def test_wide_u_requires_2r():
    assert geom_same.same_u((20.0, 0.0), (99.0, 0.0), 60.0) is None
    assert geom_same.same_u((20.0, 0.0), (100.0, 0.0), 60.0) is not None


def test_strategy_orders_are_complete_and_disjoint():
    routes, endpoints, _connectors, _validation = ports.load_plane('z2')
    frame_map = vframes.build_frames(routes, endpoints)
    expected = {route['route_id'] for route in routes}
    spec = strategies.sequential_strategy('A')
    order = strategies.build_order(routes, frame_map, spec)
    assert set(order) == expected and len(order) == 512
    spec_b = strategies.sequential_strategy('B')
    order_b = strategies.build_order(routes, frame_map, spec_b)
    assert set(order_b) == expected
    # same-side connections first for B, opposite first for A
    assert routes[0]['route_id'] in expected
    c_spec = strategies.round_robin_spec(start_side='E', direction='ccw', batch=8)
    order_c = strategies.round_robin_order(routes, frame_map, c_spec)
    assert set(order_c) == expected and len(order_c) == 512


def test_canonical_roundtrip_maps_back_to_world():
    from four_side_1024.legacy_geometry import transform_primitives
    p, q = (60.0, 0.0), (100.0, 0.0)
    primitives = geom_same.same_hairpin_a(p, q, 0.0, 1.0)
    if primitives is None:
        primitives = geom_same.same_hairpin_b(p, q, None, 1.0)
    assert primitives is not None
    transform = vframes.SAME_TRANSFORMS['W']
    world = transform_primitives(primitives, transform, inverse=True)
    back = transform_primitives(world, transform, inverse=False)
    for first, second in zip(primitives, back):
        assert first['p0'] == pytest.approx(second['p0'])
        assert first['p1'] == pytest.approx(second['p1'])
