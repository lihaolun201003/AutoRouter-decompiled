"""Tests of the R15 same-side (180 degree) U-turn geometry module.

Run from the ``OpticalWaveguideRouter2D`` project root::

    .venv\\Scripts\\python.exe -m pytest four_side_1024\\r15\\tests_r15 -q

What is pinned down here:

* the process radius is exactly R = 15 mm (and the module has no radius
  hardcode: an explicit R40 request really builds R40 geometry);
* a pure half-circle U exists **only** for a same-side separation d == 2R;
* ``straight + half-circle + straight`` (stadium) and
  ``straight + 90 arc + straight + 90 arc + straight`` (quarter pair) behave as
  documented, and the quarter pair carries the ``d - 2R`` middle straight;
* separations below 2R are rejected without shrinking the radius; the minimum
  feasible separation is reported as 30 mm at R15;
* every emitted chain passes the frozen ``fslw.geom.canonical_validate`` with
  the real same-side poses (start tangent = inward, end tangent = -inward),
  exact R = 15 arcs, axis-aligned lines and the 150 x 150 mm board;
* the four board sides are handled by rigid canonical frames;
* the real V2 / D56 port table (IEC 2x16 MPO, 0.25 mm in-plane column pitch)
  yields the expected same-side U feasibility statistics.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from four_side_1024.r15 import profile_r15

profile_r15.apply()

from four_side_1024.fslw import config as C  # noqa: E402
from four_side_1024.fslw import geom  # noqa: E402
from four_side_1024.fslw import ports  # noqa: E402
from four_side_1024.r15 import u_geometry as U  # noqa: E402

R15 = 15.0
WIDTH = 0.05
BOARD = 150.0
INWARD = {'S': (0.0, 1.0), 'N': (0.0, -1.0),
          'E': (-1.0, 0.0), 'W': (1.0, 0.0)}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def arcs(primitives):
    return [primitive for primitive in primitives if primitive['kind'] == 'arc']


def lines(primitives):
    return [primitive for primitive in primitives if primitive['kind'] == 'line']


def line_length(primitive):
    return math.hypot(primitive['p1'][0] - primitive['p0'][0],
                      primitive['p1'][1] - primitive['p0'][1])


def same_side_poses(side, first, second):
    """World p/q (and travel directions) for two ports on ``side`` sep. d."""
    inward = INWARD[side]
    edge = (-inward[1], inward[0])
    if side == 'S':
        p = (first, 0.0)
        q = (second, 0.0)
    elif side == 'N':
        p = (first, BOARD)
        q = (second, BOARD)
    elif side == 'W':
        p = (0.0, first)
        q = (0.0, second)
    else:
        p = (BOARD, first)
        q = (BOARD, second)
    return p, q, inward, (-inward[0], -inward[1])


def assert_valid(primitives, p, q, start_dir, end_dir, radius=R15):
    """Frozen canonical validation + the module's exactness/tangency contract."""
    ok, errors = geom.canonical_validate(primitives, p, q, start_dir, end_dir,
                                         radius=radius, width=WIDTH)
    assert ok, errors
    assert primitives[0]['p0'] == pytest.approx(list(p))
    assert primitives[-1]['p1'] == pytest.approx(list(q))
    for index, primitive in enumerate(primitives):
        assert primitive['kind'] in ('line', 'arc')
        assert primitive.get('layer', 0) == 0
        if primitive['kind'] == 'line':
            p0, p1 = primitive['p0'], primitive['p1']
            assert abs(p0[0] - p1[0]) <= 1e-9 or abs(p0[1] - p1[1]) <= 1e-9
        else:
            assert primitive['radius'] == pytest.approx(radius, abs=1e-12)
            assert abs(primitive['sweep']) <= 2.0 * math.pi + 1e-9
            assert abs(math.hypot(primitive['p0'][0] - primitive['center'][0],
                                  primitive['p0'][1] - primitive['center'][1])
                       - radius) <= 1e-9
        if index:
            previous = primitives[index - 1]
            assert math.hypot(previous['p1'][0] - primitive['p0'][0],
                              previous['p1'][1] - primitive['p0'][1]) <= 1e-9


# ---------------------------------------------------------------------------
# process radius
# ---------------------------------------------------------------------------
def test_profile_and_default_radius_are_r15():
    assert R15 == 15.0
    assert float(C.RADIUS_MM) == pytest.approx(15.0)
    assert U.R15_MM == pytest.approx(15.0)
    assert U.resolve_radius() == pytest.approx(15.0)
    assert U.resolve_radius(40.0) == pytest.approx(40.0)
    assert U.resolve_board() == pytest.approx(150.0)
    assert U.resolve_width() == pytest.approx(0.05)


def test_min_feasible_separation_is_2r_for_any_radius():
    # No hardcoded radius: the geometric rule is exactly 2R, whatever R is.
    assert U.min_feasible_separation() == pytest.approx(30.0)
    assert U.min_feasible_separation(15.0) == pytest.approx(30.0)
    assert U.min_feasible_separation(40.0) == pytest.approx(80.0)
    assert U.min_feasible_separation(10.0) == pytest.approx(20.0)


def test_reachability_reports_minimum_and_families():
    at_minimum = U.u_reachability(30.0)
    assert at_minimum['feasible'] is True
    assert at_minimum['minimum_separation_mm'] == pytest.approx(30.0)
    assert at_minimum['families'] == ['half_circle', 'quarter_pair', 'stadium']
    assert at_minimum['reason'] is None

    larger = U.u_reachability(45.0)
    assert larger['feasible'] is True
    assert larger['families'] == ['quarter_pair']

    below = U.u_reachability(29.999)
    assert below['feasible'] is False
    assert below['families'] == []
    assert below['reason'] == 'below_minimum_separation_no_radius_shrink'
    assert below['minimum_separation_mm'] == pytest.approx(30.0)

    coincident = U.u_reachability(0.0)
    assert coincident['feasible'] is False
    assert coincident['reason'] == 'coincident_ports'


# ---------------------------------------------------------------------------
# family geometry
# ---------------------------------------------------------------------------
def test_pure_half_circle_requires_exact_2r_separation():
    p, q, start_dir, end_dir = same_side_poses('S', 20.0, 50.0)  # d = 2R
    candidates = U.u_candidates(p, q, start_dir, end_dir)
    half = [c for c in candidates if c['family'] == 'half_circle']
    assert len(half) == 1
    primitives = half[0]['primitives']
    assert len(primitives) == 1 and primitives[0]['kind'] == 'arc'
    arc = primitives[0]
    assert abs(arc['sweep']) == pytest.approx(math.pi)
    assert arc['radius'] == pytest.approx(15.0)
    assert arc['center'] == pytest.approx([35.0, 0.0])  # (p.x + q.x) / 2
    assert half[0]['length_mm'] == pytest.approx(math.pi * 15.0)
    assert_valid(primitives, p, q, start_dir, end_dir)

    # one ULP away from 2R is *not* a pure half circle any more
    for separation in (30.0 - 1e-6, 30.0 + 1e-6):
        other = U.u_candidates((20.0, 0.0), (20.0 + separation, 0.0),
                               (0.0, 1.0), (0.0, -1.0))
        assert [c for c in other if c['family'] == 'half_circle'] == []
        if separation > 30.0:
            # d > 2R only supports the quarter-arc family
            assert other and all(c['family'] == 'quarter_pair' for c in other)
        else:
            assert other == []


def test_stadium_is_straight_half_circle_straight():
    p, q, start_dir, end_dir = same_side_poses('S', 20.0, 50.0)
    candidates = U.u_candidates(p, q, start_dir, end_dir)
    stadiums = [c for c in candidates if c['family'] == 'stadium']
    assert stadiums  # d == 2R keeps the straight+half-circle+straight family
    for candidate in stadiums:
        primitives = candidate['primitives']
        assert [primitive['kind'] for primitive in primitives] == \
            ['line', 'arc', 'line']
        assert abs(primitives[1]['sweep']) == pytest.approx(math.pi)
        bulge = candidate['params']['bulge_mm']
        assert bulge > 0.0
        assert line_length(primitives[0]) == pytest.approx(bulge)
        assert line_length(primitives[-1]) == pytest.approx(bulge)
        assert_valid(primitives, p, q, start_dir, end_dir)


def test_quarter_pair_carries_the_extra_straight_for_d_above_2r():
    d = 45.0
    p, q, start_dir, end_dir = same_side_poses('S', 20.0, 20.0 + d)
    candidates = U.u_candidates(p, q, start_dir, end_dir)
    assert candidates
    assert all(c['family'] == 'quarter_pair' for c in candidates)
    for candidate in candidates:
        primitives = candidate['primitives']
        candidate_arcs = arcs(primitives)
        assert len(candidate_arcs) == 2
        for arc in candidate_arcs:
            assert abs(abs(arc['sweep']) - math.pi / 2.0) <= 1e-12
        middle = candidate['params']['middle_straight_mm']
        assert middle == pytest.approx(d - 2.0 * R15)
        assert any(abs(line_length(primitive) - middle) <= 1e-9
                   for primitive in lines(primitives))
        assert_valid(primitives, p, q, start_dir, end_dir)
    compact = [c for c in candidates if c['params']['bulge_mm'] == 0.0]
    assert len(compact) == 1


def test_half_circle_can_also_be_split_into_two_quarter_arcs():
    p, q, start_dir, end_dir = same_side_poses('S', 20.0, 50.0)
    split = [c for c in U.u_candidates(p, q, start_dir, end_dir)
             if c['family'] == 'quarter_pair'
             and c['params']['bulge_mm'] == 0.0
             and c['params']['middle_straight_mm'] == 0.0]
    assert len(split) == 1
    primitives = split[0]['primitives']
    assert [primitive['kind'] for primitive in primitives] == ['arc', 'arc']
    assert_valid(primitives, p, q, start_dir, end_dir)


# ---------------------------------------------------------------------------
# feasibility / no radius shrink
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('separation', [0.25, 0.5, 1.0, 5.0, 10.0, 20.0,
                                        29.0, 29.75, 29.999999])
def test_infeasible_same_side_separations_are_rejected(separation):
    p, q, start_dir, end_dir = same_side_poses('S', 20.0, 20.0 + separation)
    assert U.u_candidates(p, q, start_dir, end_dir) == []
    assert U.u_reachability(separation)['feasible'] is False


def test_separations_above_2r_are_feasible_with_alternatives():
    p, q, start_dir, end_dir = same_side_poses('S', 20.0, 20.0 + 45.0)
    candidates = U.u_candidates(p, q, start_dir, end_dir)
    assert len(candidates) >= 2  # several representative bulges
    lengths = sorted(candidate['length_mm'] for candidate in candidates)
    compact = math.pi * 15.0 + (45.0 - 30.0)  # two quarter arcs + middle straight
    assert lengths[0] == pytest.approx(compact)


def test_radius_is_never_shrunk_and_is_passed_through():
    # Every emitted R15 candidate really has R = 15 arcs (never below).
    p, q, start_dir, end_dir = same_side_poses('S', 20.0, 20.0 + 60.0)
    for candidate in U.u_candidates(p, q, start_dir, end_dir):
        for arc in arcs(candidate['primitives']):
            assert arc['radius'] == pytest.approx(15.0, abs=1e-12)
    # The historical R40 convention produces R = 40 geometry, not R = 15.
    p40, q40 = (20.0, 0.0), (100.0, 0.0)  # d = 80 = 2R40
    candidates40 = U.u_candidates(p40, q40, (0.0, 1.0), (0.0, -1.0),
                                 radius=40.0)
    assert candidates40
    for candidate in candidates40:
        for arc in arcs(candidate['primitives']):
            assert arc['radius'] == pytest.approx(40.0, abs=1e-12)
        assert_valid(candidate['primitives'], p40, q40, (0.0, 1.0),
                     (0.0, -1.0), radius=40.0)
    # d = 30 is feasible at R15 but far below the R40 minimum of 80 mm.
    assert U.u_candidates((20.0, 0.0), (50.0, 0.0), (0.0, 1.0),
                          (0.0, -1.0), radius=40.0) == []
    assert U.u_reachability(30.0, radius=40.0)['feasible'] is False
    assert U.u_reachability(30.0, radius=40.0)['minimum_separation_mm'] == \
        pytest.approx(80.0)


# ---------------------------------------------------------------------------
# frozen canonical validation / poses / all board sides
# ---------------------------------------------------------------------------
@pytest.mark.parametrize('side', ['S', 'W', 'N', 'E'])
def test_all_four_board_sides_are_validated_in_world_coordinates(side):
    p, q, start_dir, end_dir = same_side_poses(side, 20.0, 50.0)  # d = 2R
    candidates = U.u_candidates(p, q, start_dir, end_dir)
    assert candidates
    families = {candidate['family'] for candidate in candidates}
    assert families == {'half_circle', 'quarter_pair', 'stadium'}
    for candidate in candidates:
        assert_valid(candidate['primitives'], p, q, start_dir, end_dir)
        assert candidate['side'] == side
    frame = U.u_frame(p, q, start_dir, end_dir)
    assert frame['valid'] is True
    assert frame['side'] == side
    assert frame['separation_mm'] == pytest.approx(30.0)
    # canonical frame: common side becomes y = 0, inward becomes +y
    assert frame['p_canonical'][1] == pytest.approx(0.0, abs=1e-9)
    assert frame['q_canonical'][1] == pytest.approx(0.0, abs=1e-9)
    assert abs(frame['q_canonical'][0] - frame['p_canonical'][0]) == \
        pytest.approx(30.0)


def test_rotated_side_geometry_is_congruent():
    s_side = U.u_candidates((20.0, 0.0), (50.0, 0.0), (0.0, 1.0), (0.0, -1.0))
    w_side = U.u_candidates((0.0, 20.0), (0.0, 50.0), (1.0, 0.0), (-1.0, 0.0))
    assert [c['family'] for c in s_side] == [c['family'] for c in w_side]
    assert [c['length_mm'] for c in s_side] == pytest.approx(
        [c['length_mm'] for c in w_side])


def test_reversed_port_order_builds_the_mirrored_u():
    p, q = (50.0, 0.0), (20.0, 0.0)
    candidates = U.u_candidates(p, q, (0.0, 1.0), (0.0, -1.0))
    assert candidates
    half = [c for c in candidates if c['family'] == 'half_circle'][0]
    arc = half['primitives'][0]
    assert arc['center'] == pytest.approx([35.0, 0.0])
    assert arc['sweep'] > 0.0  # mirrored turning direction
    assert_valid(half['primitives'], p, q, (0.0, 1.0), (0.0, -1.0))


# ---------------------------------------------------------------------------
# invalid inputs
# ---------------------------------------------------------------------------
def test_invalid_pose_combinations_are_rejected():
    p, q = (20.0, 0.0), (50.0, 0.0)
    # end tangent must be -inward
    assert U.u_candidates(p, q, (0.0, 1.0), (0.0, 1.0)) == []
    # start direction must be an inward axis
    assert U.u_candidates(p, q, (math.cos(0.3), math.sin(0.3)),
                          (0.0, -1.0)) == []
    # q must be on the same board side
    assert U.u_candidates(p, (20.0, BOARD), (0.0, 1.0), (0.0, -1.0)) == []
    # ports must lie inside the side span
    assert U.u_candidates(p, (170.0, 0.0), (0.0, 1.0), (0.0, -1.0)) == []
    # coincident ports
    assert U.u_candidates(p, p, (0.0, 1.0), (0.0, -1.0)) == []

    frame = U.u_frame(p, q, (0.0, 1.0), (0.0, 1.0))
    assert frame['valid'] is False
    assert 'end_direction_is_not_minus_inward' in frame['errors']
    frame = U.u_frame(p, (20.0, BOARD), (0.0, 1.0), (0.0, -1.0))
    assert 'target_port_off_side' in frame['errors']


def test_board_parameter_is_honoured():
    # A U needs at least R + width/2 = 15.025 mm of board depth for any bend.
    assert U.u_reachability(30.0, board=10.0)['board_fits'] is False
    assert U.u_reachability(30.0, board=10.0)['reason'] == \
        'board_too_small_for_radius'
    assert U.u_candidates((5.0, 0.0), (35.0, 0.0), (0.0, 1.0), (0.0, -1.0),
                          board=10.0) == []
    # A 40 mm board has both enough depth and enough side span for the U.
    tiny = (5.0, 0.0)
    small = (35.0, 0.0)
    candidates = U.u_candidates(tiny, small, (0.0, 1.0), (0.0, -1.0), board=40.0)
    assert candidates
    from four_side_1024.geometry import validate
    for candidate in candidates:
        errors = validate(candidate['primitives'], tiny, small, (0.0, 1.0),
                          (0.0, -1.0), board=40.0, width=WIDTH, min_radius=15.0)
        assert not errors, errors


# ---------------------------------------------------------------------------
# real V2 / D56 port table
# ---------------------------------------------------------------------------
def test_real_v2_port_table_same_side_u_statistics():
    """IEC 2x16 MPO in-plane ports: 61.6 % of same-side pairs fit at R15."""
    endpoints = ports.build_plane_endpoints()
    along = sorted({round(endpoint['routing_xy'][1], 9)
                    for endpoint in endpoints.values()
                    if endpoint['side'] == 'W' and endpoint['plane'] == 'z2'})
    assert len(along) == 256
    assert along[0] == pytest.approx(5.625)
    assert along[-1] == pytest.approx(144.375)
    assert along[1] - along[0] == pytest.approx(0.25)

    separations = [second - first
                   for index, first in enumerate(along)
                   for second in along[index + 1:]]
    assert len(separations) == 256 * 255 // 2
    r15_feasible = sum(1 for value in separations if value >= 30.0 - 1e-9)
    r40_feasible = sum(1 for value in separations if value >= 80.0 - 1e-9)
    assert r15_feasible == 20098
    assert r40_feasible == 6706
    assert r15_feasible > 2.9 * r40_feasible  # R15 (nearly) triples the count

    # a real same-side pair exactly 30 mm apart: columns 1 and 13 four
    # connectors apart (along = 5.625 and 35.625 mm) is a pure half circle.
    p = (0.0, 5.625)
    q = (0.0, 35.625)
    candidates = U.u_candidates(p, q, (1.0, 0.0), (-1.0, 0.0))
    assert [c['family'] for c in candidates].count('half_circle') == 1
    assert_valid([c for c in candidates
                  if c['family'] == 'half_circle'][0]['primitives'],
                 p, q, (1.0, 0.0), (-1.0, 0.0))
    # the nearest neighbouring columns (0.25 mm apart) are not connectable
    assert U.u_candidates((0.0, 5.625), (0.0, 5.875),
                          (1.0, 0.0), (-1.0, 0.0)) == []
