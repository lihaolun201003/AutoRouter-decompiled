"""Tests of ``four_side_1024/l3d/paths.py`` (corrected L1-L5 model, R9 round).

Run from the ``OpticalWaveguideRouter2D`` project root::

    .venv\\Scripts\\python.exe -m pytest four_side_1024\\l3d\\tests_l3d -q

Covered:

* elevation S-curve math at R = 15 mm for several dz (theta / footprint / length);
* transition placement rules: straights only, footprints and margins,
  strictly increasing positions, ``min_flat_gap`` (0 = back-to-back allowed),
  infeasible paths return ``None``;
* variant semantics (0 = earliest-then-latest, 1 = all earliest,
  2 = all latest) and per-footprint straight windows;
* ``build_route_l3d`` schema fields: layers / heights / parts / lengths /
  endpoints / flat-only / z2 row / multi-transition L1->L2->L3->L1;
* 3D join continuity (exact and sampled), radius 15 and G1 everywhere;
* real R15 2D candidate routes from
  ``outputs/four_side_1024_v2_r15_v01/planes/V2/{A,B}/{z1,z2}/routes.json``
  (flat + single-lift + multi-transition realisations; short routes skipped and
  counted).
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from four_side_1024.r15 import profile_r15

profile_r15.apply()

from four_side_1024.fsd25d import path3d as P  # noqa: E402
from four_side_1024.l3d import paths as L  # noqa: E402

R = 15.0
R15_DIR = PROJECT_ROOT / 'outputs' / 'four_side_1024_v2_r15_v01' / 'planes' / 'V2'
SCHEMA_KEYS = {
    'route_id', 'plane', 'source_row', 'target_row', 'source_port',
    'target_port', 'start_z_mm', 'end_z_mm', 'layer_sequence',
    'layer_z_sequence', 'n_transitions', 'lifted', 'layers_used',
    'xy_length_mm', 'length_mm', 'z_span_mm', 'parts',
}


# ---------------------------------------------------------------------------
# 2D path builders (D56 style primitives: axis lines + fixed-radius arcs)
# ---------------------------------------------------------------------------
def line(p0, p1):
    return dict(kind='line', p0=[float(p0[0]), float(p0[1])],
                p1=[float(p1[0]), float(p1[1])])


def arc(p0, p1, center, radius, start_angle, sweep):
    return dict(kind='arc', p0=[float(p0[0]), float(p0[1])],
                p1=[float(p1[0]), float(p1[1])],
                center=[float(center[0]), float(center[1])],
                radius=float(radius), start_angle=float(start_angle),
                sweep=float(sweep))


def quarter(start, heading, turn, radius=R):
    """One 90-degree arc; ``turn`` +1 = left, -1 = right."""
    normal = (-heading[1] * turn, heading[0] * turn)
    center = (start[0] + radius * normal[0], start[1] + radius * normal[1])
    start_angle = math.atan2(start[1] - center[1], start[0] - center[0])
    sweep = turn * math.pi / 2.0
    end = (center[0] + radius * math.cos(start_angle + sweep),
           center[1] + radius * math.sin(start_angle + sweep))
    cos_sweep, sin_sweep = math.cos(sweep), math.sin(sweep)
    heading2 = (heading[0] * cos_sweep - heading[1] * sin_sweep,
                heading[0] * sin_sweep + heading[1] * cos_sweep)
    return arc(start, end, center, radius, start_angle, sweep), end, heading2


def chain(moves, start=(10.0, 75.0), heading=(1.0, 0.0)):
    primitives = []
    cursor, direction = start, heading
    for kind, argument in moves:
        if kind == 'L':
            end = (cursor[0] + direction[0] * argument,
                   cursor[1] + direction[1] * argument)
            primitives.append(line(cursor, end))
            cursor = end
        else:
            primitive, cursor, direction = quarter(cursor, direction, argument)
            primitives.append(primitive)
    return primitives


def straight_path(length=120.0, start=(10.0, 75.0)):
    return [line(start, (start[0] + length, start[1]))]


def expected_geometry(dz):
    """Independent elevation S-curve formula at R=15."""
    theta = math.acos(1.0 - abs(float(dz)) / (2.0 * R))
    return dict(theta=theta, footprint=2.0 * R * math.sin(theta),
                length=2.0 * R * theta)


def port_meta(path, z0=0.0, row=1):
    return dict(source_port=dict(xy=list(path[0]['p0']), z_mm=z0, layer_id=1),
                target_port=dict(xy=list(path[-1]['p1']), z_mm=z0, layer_id=1),
                source_row=row, target_row=row)


def assert_placement_on_straights(prims, placement, port_margin, segment_margin):
    """Every transition footprint must be inside one straight primitive."""
    intervals = P.straight_intervals(prims)
    total = P.path_length(prims)
    footprints = placement['footprints']
    starts = placement['starts_s']
    ends = placement['ends_s']
    assert len(starts) == len(footprints)
    assert len(ends) == len(footprints)
    for index, (start, end, footprint) in enumerate(
            zip(starts, ends, footprints)):
        assert end == pytest.approx(start + footprint, abs=1e-9)
        inside = any(a + segment_margin - 1e-9 <= start
                     and end <= b - segment_margin + 1e-9
                     for a, b, _prim in intervals)
        assert inside, f'transition {index} not fully on a straight: {start}..{end}'
        if index:
            assert start >= starts[index - 1] - 1e-12
            assert end >= ends[index - 1] - 1e-12
            if placement['min_flat_gap'] > 0.0:
                assert start - ends[index - 1] >= \
                    placement['min_flat_gap'] - 1e-9
    if starts:
        assert starts[0] >= port_margin - 1e-9
        assert ends[-1] <= total - port_margin + 1e-9


# ---------------------------------------------------------------------------
# elevation S-curve math
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('dz', [0.25, 0.5, 1.0, 2.0, 3.0])
def test_transition_geometry_math_r15(dz):
    expected = expected_geometry(dz)
    geometry = L.transition_geometry(dz)
    assert geometry['dz_mm'] == pytest.approx(dz)
    assert geometry['theta_rad'] == pytest.approx(expected['theta'], abs=1e-12)
    assert geometry['footprint_mm'] == pytest.approx(expected['footprint'],
                                                     abs=1e-12)
    assert geometry['length_mm'] == pytest.approx(expected['length'], abs=1e-12)
    assert 0.0 < geometry['theta_rad'] < math.pi / 2.0
    assert 0.0 < geometry['footprint_mm'] < 2.0 * R
    # the formula is even in dz (descent == ascent geometry)
    descent = L.transition_geometry(-dz)
    assert descent['footprint_mm'] == pytest.approx(geometry['footprint_mm'])
    assert descent['length_mm'] == pytest.approx(geometry['length_mm'])


@pytest.mark.parametrize('dz', [0.25, 0.5, 1.0, 2.0, 3.0])
def test_placed_footprints_use_their_own_dz(dz):
    path = straight_path(120.0)
    placement = L.place_transitions_multi(path, [0.0, dz, 0.0], radius=R)
    assert placement is not None
    expected = expected_geometry(dz)
    assert placement['footprints'] == pytest.approx(
        [expected['footprint'], expected['footprint']], abs=1e-12)
    assert placement['ends_s'] == pytest.approx(
        [placement['starts_s'][0] + expected['footprint'],
         placement['starts_s'][1] + expected['footprint']], abs=1e-12)
    assert_placement_on_straights(path, placement, L.PORT_MARGIN_MM,
                                  L.SEGMENT_MARGIN_MM)


# ---------------------------------------------------------------------------
# placement rules
# ---------------------------------------------------------------------------
def test_no_transitions_returns_empty_placement():
    path = straight_path(50.0)
    placement = L.place_transitions_multi(path, [0.0], radius=R)
    assert placement == dict(footprints=[], starts_s=[], ends_s=[],
                             z_sequence=[0.0],
                             min_flat_gap=L.DEFAULT_MIN_FLAT_GAP_MM, variant=0)


def test_single_transition_respects_margins():
    path = straight_path(120.0)
    placement = L.place_transitions_multi(path, [0.0, 1.0], radius=R)
    assert placement is not None
    assert placement['starts_s'][0] == pytest.approx(L.PORT_MARGIN_MM)
    assert placement['ends_s'][0] <= \
        P.path_length(path) - L.PORT_MARGIN_MM + 1e-9
    assert_placement_on_straights(path, placement, L.PORT_MARGIN_MM,
                                  L.SEGMENT_MARGIN_MM)


def test_variant_semantics_earliest_then_latest():
    path = straight_path(120.0)
    total = P.path_length(path)
    footprint = expected_geometry(1.5)['footprint']
    variants = {variant: L.place_transitions_multi(
        path, [0.0, 1.5, 0.0], radius=R, variant=variant, min_flat_gap=0.0)
        for variant in (0, 1, 2)}
    assert all(value is not None for value in variants.values())
    early = variants[1]
    late = variants[2]
    mixed = variants[0]
    # variant 1: all transitions as early as possible
    assert early['starts_s'][0] == pytest.approx(L.PORT_MARGIN_MM)
    assert early['starts_s'][1] == pytest.approx(L.PORT_MARGIN_MM + footprint)
    # variant 2: all transitions as late as possible
    assert late['ends_s'][-1] == pytest.approx(total - L.PORT_MARGIN_MM)
    assert late['ends_s'][0] == pytest.approx(late['starts_s'][1])
    # variant 0: first as early as possible, last as late as possible
    assert mixed['starts_s'][0] == pytest.approx(L.PORT_MARGIN_MM)
    assert mixed['ends_s'][-1] == pytest.approx(total - L.PORT_MARGIN_MM)
    assert mixed['starts_s'][1] > early['starts_s'][1]
    for variant in (0, 1, 2):
        assert_placement_on_straights(path, variants[variant],
                                      L.PORT_MARGIN_MM, L.SEGMENT_MARGIN_MM)
        assert variants[variant]['variant'] == variant


def test_back_to_back_transitions_allowed_with_zero_gap():
    path = straight_path(120.0)
    footprint = expected_geometry(1.0)['footprint']
    placement = L.place_transitions_multi(path, [0.0, 1.0, 2.0], radius=R,
                                          min_flat_gap=0.0, variant=1)
    assert placement is not None
    assert placement['starts_s'][1] == pytest.approx(
        placement['ends_s'][0], abs=1e-9)
    assert placement['starts_s'][1] == pytest.approx(
        L.PORT_MARGIN_MM + footprint)
    assert_placement_on_straights(path, placement, L.PORT_MARGIN_MM,
                                  L.SEGMENT_MARGIN_MM)


@pytest.mark.parametrize('gap', [2.0, 5.0, 10.0])
def test_min_flat_gap_is_respected(gap):
    path = straight_path(120.0)
    for variant in (0, 1, 2):
        placement = L.place_transitions_multi(
            path, [0.0, 1.0, 2.0], radius=R, min_flat_gap=gap,
            variant=variant)
        assert placement is not None
        assert placement['starts_s'][1] - placement['ends_s'][0] >= \
            gap - 1e-9
        assert placement['min_flat_gap'] == pytest.approx(gap)


def test_three_transitions_on_long_straight():
    path = straight_path(120.0)
    z_sequence = [0.0, 1.0, 1.5, 0.0]
    footprints = [expected_geometry(z_sequence[i + 1] - z_sequence[i])['footprint']
                  for i in range(3)]
    placement = L.place_transitions_multi(path, z_sequence, radius=R)
    assert placement is not None
    assert placement['z_sequence'] == pytest.approx(z_sequence)
    assert placement['footprints'] == pytest.approx(footprints, abs=1e-12)
    assert len(placement['starts_s']) == 3
    for index in range(1, 3):
        assert placement['starts_s'][index] >= \
            placement['ends_s'][index - 1] - 1e-9
    assert_placement_on_straights(path, placement, L.PORT_MARGIN_MM,
                                  L.SEGMENT_MARGIN_MM)


def test_transitions_are_placed_on_their_own_footprint_window():
    # line(10) + quarter arc + line(30): the second (large) footprint cannot fit
    # on the first short straight, so it must land on the second one.
    path = chain([('L', 10.0), ('Q', -1), ('L', 30.0)])
    intervals = P.straight_intervals(path)
    assert len(intervals) == 2
    second_start = intervals[1][0]
    placement = L.place_transitions_multi(path, [0.0, 1.0, 4.0], radius=R,
                                          variant=1)
    assert placement is not None
    assert placement['starts_s'][0] < second_start  # small dz on first line
    assert placement['starts_s'][1] >= second_start - 1e-9  # large dz on second
    assert_placement_on_straights(path, placement, L.PORT_MARGIN_MM,
                                  L.SEGMENT_MARGIN_MM)


@pytest.mark.parametrize('variant', [0, 1, 2])
def test_bent_path_placement_is_legal(variant):
    path = chain([('L', 20.0), ('Q', -1), ('L', 40.0), ('Q', 1), ('L', 20.0)])
    placement = L.place_transitions_multi(path, [0.0, 1.5, 0.0], radius=R,
                                          variant=variant)
    assert placement is not None
    assert_placement_on_straights(path, placement, L.PORT_MARGIN_MM,
                                  L.SEGMENT_MARGIN_MM)


# ---------------------------------------------------------------------------
# infeasible input
# ---------------------------------------------------------------------------
def test_short_path_returns_none():
    assert L.place_transitions_multi(straight_path(3.0), [0.0, 1.0],
                                     radius=R) is None
    assert L.place_transitions_multi(straight_path(20.0), [0.0, 1.5, 0.0],
                                     radius=R) is None


def test_path_without_straights_returns_none():
    # a half circle built from two quarter arcs has no line primitive at all
    start = (10.0, 75.0)
    first, middle, heading = quarter(start, (1.0, 0.0), -1)
    second, _end, _heading = quarter(middle, heading, -1)
    assert L.place_transitions_multi([first, second], [0.0, 1.0],
                                     radius=R) is None


def test_footprint_larger_than_every_straight_returns_none():
    path = straight_path(10.0)
    # dz = 10 mm has footprint 22.36 mm > the 10 mm straight
    assert L.place_transitions_multi(path, [0.0, 10.0], radius=R) is None


def test_dz_beyond_frozen_helper_domain_returns_none():
    path = straight_path(120.0)
    # |dz| >= 4R is outside acos(1 - dz/(2R))
    assert L.place_transitions_multi(path, [0.0, 4.0 * R + 1.0],
                                     radius=R) is None


def test_invalid_arguments_raise():
    path = straight_path(50.0)
    with pytest.raises(ValueError):
        L.place_transitions_multi(path, [0.0, 1.0], radius=0.0)
    with pytest.raises(ValueError):
        L.place_transitions_multi(path, [0.0, 1.0], variant=5)
    with pytest.raises(ValueError):
        L.place_transitions_multi(path, [0.0, 1.0], min_flat_gap=-1.0)
    with pytest.raises(ValueError):
        L.place_transitions_multi(path, [float('nan'), 1.0])


# ---------------------------------------------------------------------------
# build_route_l3d: schema and geometry
# ---------------------------------------------------------------------------
def test_build_route_single_lift_structure():
    path = straight_path(120.0)
    meta = port_meta(path, z0=0.0, row=1)
    route = L.build_route_l3d(7, 'z1', path, [1, 2, 1], [0.0, 2.5, 0.0], meta)
    assert route is not None
    assert set(route) == SCHEMA_KEYS
    assert route['route_id'] == 7
    assert route['plane'] == 'z1'
    assert route['source_row'] == route['target_row'] == 1
    assert route['start_z_mm'] == pytest.approx(0.0)
    assert route['end_z_mm'] == pytest.approx(0.0)
    assert route['layer_sequence'] == [1, 2, 1]
    assert route['layer_z_sequence'] == pytest.approx([0.0, 2.5, 0.0])
    assert route['n_transitions'] == 2
    assert route['lifted'] is True
    assert route['layers_used'] == [1, 2]
    assert route['z_span_mm'] == pytest.approx(2.5)
    assert route['source_port'] == dict(xy=[10.0, 75.0], z_mm=0.0, layer_id=1)
    assert route['target_port'] == dict(xy=[130.0, 75.0], z_mm=0.0, layer_id=1)

    kinds = [part['kind'] for part in route['parts']]
    assert kinds == ['flat', 'transition', 'flat', 'transition', 'flat']
    flats = [part for part in route['parts'] if part['kind'] == 'flat']
    assert [part['layer_id'] for part in flats] == [1, 2, 1]
    assert [part['z_mm'] for part in flats] == pytest.approx([0.0, 2.5, 0.0])
    assert flats[0]['length_mm'] == pytest.approx(L.PORT_MARGIN_MM)
    assert flats[-1]['length_mm'] == pytest.approx(L.PORT_MARGIN_MM)
    # flat sub-chains are actual XY sub-chains of the input path
    assert flats[0]['primitives'][0]['p0'] == pytest.approx([10.0, 75.0])
    assert flats[-1]['primitives'][-1]['p1'] == pytest.approx([130.0, 75.0])
    expected = expected_geometry(2.5)
    transitions = [part for part in route['parts']
                   if part['kind'] == 'transition']
    for transition in transitions:
        assert transition['radius_mm'] == pytest.approx(R)
        assert transition['theta_rad'] == pytest.approx(expected['theta'])
        assert transition['footprint_mm'] == pytest.approx(expected['footprint'])
        assert transition['length_mm'] == pytest.approx(expected['length'])
    assert transitions[0]['from_layer'] == 1
    assert transitions[0]['to_layer'] == 2
    assert transitions[0]['z0'] == pytest.approx(0.0)
    assert transitions[0]['z1'] == pytest.approx(2.5)
    assert transitions[1]['z0'] == pytest.approx(2.5)
    assert transitions[1]['z1'] == pytest.approx(0.0)
    assert transitions[1]['dz_mm'] == pytest.approx(-2.5)


def test_build_route_length_accounting():
    path = straight_path(120.0)
    meta = port_meta(path)
    route = L.build_route_l3d(1, 'z1', path, [1, 2, 1], [0.0, 2.5, 0.0], meta)
    assert route is not None
    xy_length = P.path_length(path)
    flats = [part for part in route['parts'] if part['kind'] == 'flat']
    transitions = [part for part in route['parts']
                   if part['kind'] == 'transition']
    assert route['xy_length_mm'] == pytest.approx(xy_length)
    assert sum(part['length_mm'] for part in flats) + \
        sum(part['footprint_mm'] for part in transitions) == \
        pytest.approx(xy_length, abs=1e-9)
    expected_length = xy_length + sum(
        part['length_mm'] - part['footprint_mm'] for part in transitions)
    assert route['length_mm'] == pytest.approx(expected_length, abs=1e-9)
    assert route['length_mm'] == pytest.approx(
        sum(part['length_mm'] for part in route['parts']), abs=1e-12)


def test_build_route_multi_transition_l1_l2_l3_l1():
    path = straight_path(120.0)
    meta = port_meta(path)
    layers = [1, 2, 3, 1]
    heights = [0.0, 1.0, 1.5, 0.0]
    route = L.build_route_l3d(11, 'z1', path, layers, heights, meta)
    assert route is not None
    assert route['n_transitions'] == 3
    assert route['layer_sequence'] == layers
    assert route['layer_z_sequence'] == pytest.approx(heights)
    assert route['layers_used'] == [1, 2, 3]
    assert route['z_span_mm'] == pytest.approx(1.5)
    kinds = [part['kind'] for part in route['parts']]
    assert kinds == ['flat', 'transition', 'flat', 'transition', 'flat',
                     'transition', 'flat']
    middle_flats = [part for part in route['parts'] if part['kind'] == 'flat']
    assert [part['layer_id'] for part in middle_flats] == [1, 2, 3, 1]
    assert [part['z_mm'] for part in middle_flats] == pytest.approx(
        [0.0, 1.0, 1.5, 0.0])
    transitions = [part for part in route['parts']
                   if part['kind'] == 'transition']
    assert [(part['from_layer'], part['to_layer']) for part in transitions] == \
        [(1, 2), (2, 3), (3, 1)]
    for part, dz in zip(transitions, [1.0, 0.5, -1.5]):
        expected = expected_geometry(dz)
        assert part['theta_rad'] == pytest.approx(expected['theta'])
        assert part['footprint_mm'] == pytest.approx(expected['footprint'])


def test_build_route_flat_only():
    path = straight_path(50.0)
    meta = port_meta(path, z0=0.5, row=2)
    route = L.build_route_l3d(3, 'z2', path, [1], [0.5], meta)
    assert route is not None
    assert route['n_transitions'] == 0
    assert route['lifted'] is False
    assert route['layers_used'] == [1]
    assert route['z_span_mm'] == pytest.approx(0.0)
    assert route['layer_sequence'] == [1]
    assert route['layer_z_sequence'] == pytest.approx([0.5])
    assert route['start_z_mm'] == pytest.approx(0.5)
    assert route['end_z_mm'] == pytest.approx(0.5)
    assert [part['kind'] for part in route['parts']] == ['flat']
    assert route['parts'][0]['z_mm'] == pytest.approx(0.5)
    assert route['parts'][0]['layer_id'] == 1
    assert route['xy_length_mm'] == pytest.approx(50.0)
    assert route['length_mm'] == pytest.approx(50.0)


@pytest.mark.parametrize('variant', [0, 1, 2])
def test_build_route_variants_are_legal(variant):
    path = straight_path(120.0)
    meta = port_meta(path)
    route = L.build_route_l3d(9, 'z1', path, [1, 2, 1], [0.0, 1.5, 0.0],
                              meta, variant=variant)
    assert route is not None
    assert_route_structure(route, [1, 2, 1], [0.0, 1.5, 0.0])
    joins = L.route_transition_join(route)
    assert joins
    assert all(join['position_ok'] and join['tangent_ok'] for join in joins)
    # the assembled parts always alternate flat/transition/flat: the build keeps
    # DEFAULT_BUILD_MIN_FLAT_GAP_MM between consecutive transitions
    kinds = [part['kind'] for part in route['parts']]
    assert kinds == ['flat', 'transition', 'flat', 'transition', 'flat']
    transitions = [part for part in route['parts']
                   if part['kind'] == 'transition']
    flats = [part for part in route['parts'] if part['kind'] == 'flat']
    assert flats[1]['length_mm'] >= L.DEFAULT_BUILD_MIN_FLAT_GAP_MM - 1e-9
    # variant diversity: 1 climbs early, 2 climbs late, 0 earliest+latest
    first_starts = {}
    for value in (0, 1, 2):
        built = L.build_route_l3d(9, 'z1', path, [1, 2, 1], [0.0, 1.5, 0.0],
                                  meta, variant=value)
        assert built is not None
        first_starts[value] = built['parts'][0]['length_mm']
    assert first_starts[0] == pytest.approx(L.PORT_MARGIN_MM)
    assert first_starts[1] == pytest.approx(L.PORT_MARGIN_MM)
    assert first_starts[2] > first_starts[1]


def test_build_route_z2_row_height():
    path = straight_path(120.0)
    meta = port_meta(path, z0=0.5, row=2)
    route = L.build_route_l3d(5, 'z2', path, [1, 5, 1], [0.5, 2.5, 0.5], meta)
    assert route is not None
    assert route['plane'] == 'z2'
    assert route['source_row'] == 2
    assert route['target_row'] == 2
    assert route['start_z_mm'] == pytest.approx(0.5)
    assert route['end_z_mm'] == pytest.approx(0.5)
    flats = [part for part in route['parts'] if part['kind'] == 'flat']
    assert [part['z_mm'] for part in flats] == pytest.approx([0.5, 2.5, 0.5])
    assert route['source_port']['z_mm'] == pytest.approx(0.5)
    assert route['z_span_mm'] == pytest.approx(2.0)


def test_build_route_infeasible_returns_none():
    path = straight_path(20.0)
    meta = port_meta(path)
    assert L.build_route_l3d(1, 'z1', path, [1, 2, 1], [0.0, 1.5, 0.0],
                             meta) is None


def test_build_route_rejects_invalid_inputs():
    path = straight_path(120.0)
    meta = port_meta(path)
    with pytest.raises(ValueError):
        L.build_route_l3d(1, 'z9', path, [1, 2, 1], [0.0, 1.0, 0.0], meta)
    with pytest.raises(ValueError):
        L.build_route_l3d(1, 'z1', path, [1, 2], [0.0, 1.0, 0.0], meta)
    with pytest.raises(ValueError):
        L.build_route_l3d(1, 'z1', path, [2, 3, 2], [0.0, 1.0, 0.0], meta)
    with pytest.raises(ValueError):
        L.build_route_l3d(1, 'z1', path, [1, 2, 1], [0.5, 1.0, 0.5], meta)
    with pytest.raises(ValueError):
        L.build_route_l3d(1, 'z1', path, [1, 2, 1], [0.0, 1.0, 0.0],
                          port_meta(path, z0=0.5, row=2))
    bad = port_meta(path)
    bad['target_port'] = dict(xy=[0.0, 0.0], z_mm=0.0, layer_id=1)
    with pytest.raises(ValueError):
        L.build_route_l3d(1, 'z1', path, [1, 2, 1], [0.0, 1.0, 0.0], bad)


# ---------------------------------------------------------------------------
# 3D continuity
# ---------------------------------------------------------------------------
def test_route_transition_join_metrics_are_zero():
    path = chain([('L', 25.0), ('Q', -1), ('L', 50.0), ('Q', 1), ('L', 25.0)])
    meta = port_meta(path)
    route = L.build_route_l3d(2, 'z1', path, [1, 2, 1], [0.0, 1.5, 0.0], meta)
    assert route is not None
    joins = L.route_transition_join(route)
    assert len(joins) == len(route['parts']) - 1
    for join in joins:
        assert join['position_gap_mm'] <= 1e-7
        assert join['z_gap_mm'] <= 1e-9
        assert join['tangent_error_deg'] <= 1e-6
        assert join['position_ok'] and join['tangent_ok']


def part_samples_3d(part, step_flat=0.05, step_transition=0.005):
    """3D samples of one part (flat or transition)."""
    if part['kind'] == 'flat':
        primitives = part['primitives']
        length = P.path_length(primitives)
        z = float(part['z_mm'])
        count = max(2, int(math.ceil(length / step_flat)) + 1)
        points = []
        for index in range(count + 1):
            xy, _tangent = P.path_point_at(primitives, length * index / count)
            points.append((xy[0], xy[1], z))
        return points
    return [tuple(sample) for sample in
            P.transition_samples(part, step=step_transition)]


def tangent_angle_deg(first, second):
    def unit(vector):
        length = math.sqrt(sum(value * value for value in vector))
        return tuple(value / length for value in vector)
    def difference(a, b):
        return (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    def angle(u, v):
        dot = sum(a * b for a, b in zip(u, v))
        return math.degrees(math.acos(max(-1.0, min(1.0, dot))))
    left = unit(difference(first[-2], first[-1]))
    right = unit(difference(second[0], second[1]))
    return angle(left, right)


def test_3d_join_continuity_from_sampled_polyline():
    path = chain([('L', 30.0), ('Q', -1), ('L', 40.0), ('Q', 1), ('L', 30.0)])
    meta = port_meta(path)
    route = L.build_route_l3d(4, 'z1', path, [1, 3, 1], [0.0, 1.5, 0.0], meta)
    assert route is not None
    parts = route['parts']
    samples = [part_samples_3d(part) for part in parts]
    for index in range(len(parts) - 1):
        first = samples[index]
        second = samples[index + 1]
        gap = math.dist(first[-1], second[0])
        assert gap <= 1e-9
        angle = tangent_angle_deg(first, second)
        # first segment of the transition approximates its horizontal tangent
        assert angle <= 2.0, (parts[index]['kind'], parts[index + 1]['kind'],
                              angle)


def test_transition_samples_are_radius_r_and_g1():
    dz = 1.5
    transition = P.make_transition((20.0, 75.0), (1.0, 0.0), 0.0, dz, R)
    samples = [tuple(sample) for sample in
               P.transition_samples(transition, step=0.002)]
    assert len(samples) > 100
    assert samples[0][0] == pytest.approx(transition['start'][0])
    assert samples[0][1] == pytest.approx(transition['start'][1])
    assert samples[0][2] == pytest.approx(0.0)
    assert samples[-1][0] == pytest.approx(transition['end'][0])
    assert samples[-1][2] == pytest.approx(dz)
    # sampled circumradius of consecutive triples (skip triples at the inflection)
    half = R * transition['theta_rad']
    count = max(2, int(math.ceil(half / 0.002)))
    inflection = count
    radii = []
    for index in range(1, len(samples) - 1):
        if not (index + 1 <= inflection or index - 1 >= inflection):
            continue
        a, b, c = samples[index - 1], samples[index], samples[index + 1]
        ab = math.dist(a, b)
        bc = math.dist(b, c)
        ca = math.dist(c, a)
        area = _triangle_area(a, b, c)
        if area <= 1e-12:
            continue
        radii.append(ab * bc * ca / (4.0 * area))
    assert radii
    assert min(radii) == pytest.approx(R, rel=1e-3)
    assert max(radii) == pytest.approx(R, rel=1e-3)
    # horizontal tangents at both ends (vertical component ~ 0)
    first_step = tuple(samples[1][k] - samples[0][k] for k in range(3))
    last_step = tuple(samples[-1][k] - samples[-2][k] for k in range(3))
    assert abs(first_step[2]) / math.hypot(first_step[0], first_step[1]) < 1e-4
    assert abs(last_step[2]) / math.hypot(last_step[0], last_step[1]) < 1e-4


def _triangle_area(a, b, c):
    u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    cross = (u[1] * v[2] - u[2] * v[1],
             u[2] * v[0] - u[0] * v[2],
             u[0] * v[1] - u[1] * v[0])
    return 0.5 * math.sqrt(sum(value * value for value in cross))


# ---------------------------------------------------------------------------
# real R15 2D candidate routes
# ---------------------------------------------------------------------------
def assert_route_structure(route, layers, heights):
    """Schema/geometry invariants of one route (middle flats may be length 0)."""
    assert route['n_transitions'] == len(layers) - 1
    assert route['layer_sequence'] == layers
    assert route['layer_z_sequence'] == pytest.approx(heights)
    parts = route['parts']
    assert parts[0]['kind'] == 'flat'
    assert parts[-1]['kind'] == 'flat'
    assert parts[0]['layer_id'] == 1
    assert parts[0]['z_mm'] == pytest.approx(heights[0])
    assert parts[-1]['layer_id'] == 1
    assert parts[-1]['z_mm'] == pytest.approx(heights[-1])
    transitions = [part for part in parts if part['kind'] == 'transition']
    assert [(part['from_layer'], part['to_layer']) for part in transitions] == \
        list(zip(layers, layers[1:]))
    deltas = [heights[index + 1] - heights[index]
              for index in range(len(heights) - 1)]
    for part, dz in zip(transitions, deltas):
        expected = expected_geometry(dz)
        assert part['radius_mm'] == pytest.approx(R)
        assert part['theta_rad'] == pytest.approx(expected['theta'])
        assert part['footprint_mm'] == pytest.approx(expected['footprint'])
        assert part['length_mm'] == pytest.approx(expected['length'])
    # flat layer ids follow the layer sequence order (missing = zero-length flat)
    flats = [part for part in parts if part['kind'] == 'flat']
    layer_index = 0
    for flat in flats:
        while layer_index < len(layers) and layers[layer_index] != flat['layer_id']:
            layer_index += 1
        assert layer_index < len(layers)
        assert flat['z_mm'] == pytest.approx(heights[layer_index])
    # XY bookkeeping
    flat_length = sum(part['length_mm'] for part in flats)
    footprints = sum(part['footprint_mm'] for part in transitions)
    assert flat_length + footprints == pytest.approx(route['xy_length_mm'],
                                                     abs=1e-9)
    assert route['length_mm'] == pytest.approx(
        sum(part['length_mm'] for part in parts), abs=1e-12)


def load_r15_routes(scheme, plane):
    path = R15_DIR / scheme / plane / 'routes.json'
    if not path.exists():
        return None, path
    payload = json.loads(path.read_text(encoding='utf-8'))
    records = [record for record in payload['routes']
               if record.get('status') == 'routed']
    return records, path


def test_real_r15_candidates_build_flat_single_and_multi():
    if not R15_DIR.exists():
        pytest.skip('R15 2D outputs are not available')
    counts = Counter()
    sampled = 0
    checked_structure = 0
    for scheme in ('A', 'B'):
        for plane in ('z1', 'z2'):
            records, path = load_r15_routes(scheme, plane)
            if records is None:
                pytest.skip(f'missing {path}')
            z0 = 0.0 if plane == 'z1' else 0.5
            row = 1 if plane == 'z1' else 2
            for record in records[:128]:
                primitives = [P.clean_primitive(primitive)
                              for primitive in record['primitives']]
                meta = dict(
                    source_port=dict(xy=list(primitives[0]['p0']), z_mm=z0,
                                     layer_id=1),
                    target_port=dict(xy=list(primitives[-1]['p1']), z_mm=z0,
                                     layer_id=1),
                    source_row=row, target_row=row)
                sampled += 1
                flat = L.build_route_l3d(record['route_id'], plane,
                                         primitives, [1], [z0], meta)
                assert flat is not None
                counts['flat'] += 1
                single = L.build_route_l3d(record['route_id'], plane,
                                           primitives, [1, 5, 1],
                                           [z0, 2.5, z0], meta)
                if single is not None:
                    counts['single'] += 1
                    assert_route_structure(single, [1, 5, 1], [z0, 2.5, z0])
                    assert L.route_transition_join(single)
                    checked_structure += 1
                multi = L.build_route_l3d(record['route_id'], plane,
                                          primitives, [1, 2, 3, 1],
                                          [z0, 1.0, 1.5, z0], meta)
                if multi is not None:
                    counts['multi'] += 1
                    assert_route_structure(multi, [1, 2, 3, 1],
                                           [z0, 1.0, 1.5, z0])
                    joins = L.route_transition_join(multi)
                    assert all(join['position_ok'] and join['tangent_ok']
                               for join in joins)
                    assert multi['source_port']['xy'] == \
                        pytest.approx(list(primitives[0]['p0']))
                    assert multi['target_port']['xy'] == \
                        pytest.approx(list(primitives[-1]['p1']))
                    checked_structure += 1
    # short routes are legitimately skipped by the placement, but the sample is
    # expected to be mostly liftable (measured > 450 / 512 for both realisations)
    assert sampled > 0
    assert counts['flat'] == sampled
    assert counts['single'] >= 300
    assert counts['multi'] >= 300
    assert checked_structure >= 600
