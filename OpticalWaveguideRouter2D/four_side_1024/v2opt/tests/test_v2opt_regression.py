"""Regression tests of the V2 optimisation round (T4 / task 9, nine checks).

Every test asserts *real* behaviour of the shipped modules on the already
accepted BASE plane solution under
``outputs/four_side_1024_v2_candidate_rr_v01`` (regenerate it with
``.venv\\Scripts\\python.exe four_side_1024\\v2opt\\audit_baseline.py``).  No
network, no routing search over the full problem: only BASE z2 / a small
deterministic sub-layout are used, so the whole file runs in well under a minute.

Task-9 coverage
---------------
1. ``test_1_history_layout_loads`` - a historical successful layout is loaded
   correctly: ``LayoutState.from_history`` rebuilds 206/512 routed primitives
   deep-equal to the historical file and ``verify()`` passes.
2. ``test_2_index_remove_readd_restores_state`` - removing routes from the exact
   conflict index and adding them back restores the index *and* the canonical
   occupancy oracles exactly; no cell/oracle residue is left behind.
3. ``test_3_candidate_dedupe_keeps_distinct_geometry`` - the candidate de-dupe
   keeps two genuinely different legal tracks and collapses the identical one.
4. ``test_4_rr_failed_transaction_rolls_back_completely`` - a failed R&R
   transaction (illegal placement, net gain <= 0, target not placed) returns
   False and leaves accepted/failed/index/oracle state exactly as before.
5. ``test_5_transaction_never_places_one_connection_twice`` - a transaction
   result is consistent and never places one connection twice; after commit the
   index has exactly one entry per accepted route.
6. ``test_6_commit_result_only_returns_true_on_strict_growth`` - ``commit_result``
   returns True only when the routed count strictly increases; zero-gain and
   invalid placements are rejected without changing the count.
7. ``test_7_checkpoint_restores_real_geometry`` - a geometry checkpoint restored
   with ``load_layout_from_checkpoint`` gives the same routed count, the same
   primitives and the same ``verify()`` result as the historical best solution.
8. ``test_8_candidate_budget_does_not_change_physics`` - raising the candidate
   budget 200 -> 1600 changes neither the index configuration (width/gap/
   clearance/radius) nor the physical checks of a placed route (frozen validator
   single-route predicate still passes).
9. ``test_9_final_layout_reaudited_by_frozen_validator`` - the final BASE
   layout is re-audited from its primitives by the frozen authoritative
   ``validate_fslw`` strict validator (passed=True, 0 violations).

Run from ``OpticalWaveguideRouter2D``::

    .venv\\Scripts\\python.exe -m pytest four_side_1024\\v2opt\\tests -q
"""
from __future__ import annotations

import copy
import json
import math
import sys
from collections import Counter
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from four_side_1024.d56 import index as d56_index  # noqa: E402
from four_side_1024.fslw import config as fslw_config  # noqa: E402
from four_side_1024.fslw import validate_fslw  # noqa: E402
from four_side_1024.v2opt import candext  # noqa: E402
from four_side_1024.v2opt import config as v2_config  # noqa: E402
from four_side_1024.v2opt import rr  # noqa: E402
from four_side_1024.v2opt import search  # noqa: E402
from four_side_1024.v2opt.core import (  # noqa: E402
    LayoutState, load_layout_from_checkpoint, new_index, router_cfg)

OUT_ROOT = PROJECT_ROOT / 'outputs' / 'four_side_1024_v2_candidate_rr_v01'
BASE_PLANES = {
    'z1': OUT_ROOT / 'planes' / 'V2' / 'BASE' / 'z1' / 'routes.json',
    'z2': OUT_ROOT / 'planes' / 'V2' / 'BASE' / 'z2' / 'routes.json',
}
FINAL_VALIDATION = OUT_ROOT / 'final_validation.json'
ROUTES_PER_PLANE = 512
BASE_Z1_ROUTED = 492
BASE_Z2_ROUTED = 206
BASE_Z2_CROSSINGS = 7020

pytestmark = pytest.mark.skipif(
    not all(path.exists() for path in BASE_PLANES.values()),
    reason='V2 BASE plane artefacts missing: run '
           'four_side_1024/v2opt/audit_baseline.py first')


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def silent(*_args, **_kwargs):
    """Swallow the progress logging of the production modules."""


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def index_cells_signature(index):
    """Canonical form of the exact conflict index bucketing."""
    return sorted((key, tuple(sorted(bucket)))
                  for key, bucket in index._cells.items())


def oracle_signature(state):
    """Canonical form of the six canonical-frame occupancy oracles."""
    return {key: (tuple(oracle.h), tuple(oracle.v))
            for key, oracle in state.oracles.oracles.items()}


def state_signature(state):
    """accepted / failed / index / oracle snapshot used by rollback tests."""
    return {
        'accepted': sorted(state.accepted),
        'failed': copy.deepcopy(state.failed),
        'index': index_cells_signature(state.index),
        'oracles': oracle_signature(state),
    }


def base_z2_state():
    return LayoutState.from_history('V2', 'z2', BASE_PLANES['z2'], log=silent)


def small_layout(count=24, step=9):
    """Deterministic sparse z2 layout recombined from real BASE primitives.

    Every non-selected connection is carried as a *failed* record so the dump is
    a complete 512-connection plane and ``LayoutState.from_dump(dump)`` can be
    re-audited by ``verify()`` (accepted + failed partition the CSV routes).
    """
    payload = load_json(BASE_PLANES['z2'])
    records = payload['routes']
    routed = [record for record in records if record.get('status') == 'routed']
    chosen = routed[::step][:count]
    chosen_ids = {record['route_id'] for record in chosen}
    assert chosen
    dump = {
        'schema': 'four_side_1024_v2opt_layout_dump_v1',
        'topology': 'V2',
        'plane': 'z2',
        'routed': [dict(route_id=record['route_id'],
                        primitives=record['primitives'],
                        family=(record.get('candidate') or {}).get('family'),
                        params=(record.get('candidate') or {}).get('params') or {})
                   for record in chosen],
        'failed': {str(record['route_id']): dict(
            route_id=record['route_id'],
            reason=record.get('reason') or 'not_attempted',
            evaluated=int(record.get('evaluated') or 0),
            rejection_counts=dict(record.get('rejection_counts') or {}),
            blockers=dict(record.get('blockers') or {}))
            for record in records if record['route_id'] not in chosen_ids},
    }
    state = LayoutState.from_dump(dump, log=silent)
    return state, [record['route_id'] for record in chosen], payload


def free_synthetic_line(state):
    """First short horizontal line in free board space (real index evaluation)."""
    for half_steps in range(4, 296):        # y = 2.0 .. 147.5 mm
        y = half_steps * 0.5
        primitives = [{'kind': 'line', 'p0': [20.0, y], 'p1': [21.0, y]}]
        try:
            prepared = d56_index.prepare(primitives)
        except ValueError:  # pragma: no cover - defensive
            continue
        if state.index.evaluate(prepared).valid:
            return primitives
    raise AssertionError('no free synthetic line found on the sparse/base layout')


def assert_index_has_no_duplicate_entries(index):
    """One exact entry per (route, primitive) and no repeated route ids."""
    assert len(index.routes) == len(set(index.routes))
    assert set(index._route_cells) == set(index.routes)
    for key, bucket in index._cells.items():
        assert len(bucket) == len(set(map(tuple, bucket))), (
            f'duplicate index entry in cell {key}: {bucket}')


# ---------------------------------------------------------------------------
# test 1: historical successful layout loads correctly
# ---------------------------------------------------------------------------
@pytest.fixture(scope='module')
def base_z2():
    return base_z2_state()


@pytest.fixture(scope='module')
def base_z2_verify(base_z2):
    return base_z2.verify()


def test_1_history_layout_loads(base_z2, base_z2_verify):
    payload = load_json(BASE_PLANES['z2'])
    records = payload['routes']
    routed = [record for record in records if record['status'] == 'routed']
    assert len(records) == ROUTES_PER_PLANE
    assert len(routed) == BASE_Z2_ROUTED

    # the live layout is reconstructed from real primitives, not from route ids
    assert len(base_z2.accepted) == BASE_Z2_ROUTED
    assert len(base_z2.failed) == ROUTES_PER_PLANE - BASE_Z2_ROUTED
    for record in routed:
        result = base_z2.accepted[record['route_id']]
        assert result.primitives == record['primitives'], (
            f'route {record["route_id"]}: loaded primitives differ from history')
        assert result.length_mm == pytest.approx(record['length_mm'])
        assert result.prepared.length == pytest.approx(record['length_mm'])

    # independent exact re-audit of the reconstructed layout
    info = base_z2_verify
    assert info['audit_passed'] is True
    assert info['routed'] == BASE_Z2_ROUTED
    assert info['failed'] == ROUTES_PER_PLANE - BASE_Z2_ROUTED
    assert info['index_routes'] == BASE_Z2_ROUTED
    assert info['invalid'] == []
    assert info['identity_error_count'] == 0


# ---------------------------------------------------------------------------
# test 2: conflict index rip-up / re-add restores the state exactly
# ---------------------------------------------------------------------------
def test_2_index_remove_readd_restores_state():
    state = base_z2_state()
    route_ids = sorted(state.accepted)[:6]
    saved = {route_id: state.accepted[route_id] for route_id in route_ids}
    cells_before = index_cells_signature(state.index)
    oracles_before = oracle_signature(state)

    # the six routes are legal in the complete layout (leave-one-out oracle)
    for route_id in route_ids:
        assert state.index.evaluate(saved[route_id].prepared,
                                    exclude=[route_id]).valid is True

    for route_id in route_ids:
        state.remove(route_id)
    assert len(state.accepted) == BASE_Z2_ROUTED - len(route_ids)
    assert len(state.index) == BASE_Z2_ROUTED - len(route_ids)
    assert all(route_id not in state.index.routes for route_id in route_ids)
    # no cell residue
    cell_route_ids = {entry[0] for bucket in state.index._cells.values()
                      for entry in bucket}
    assert cell_route_ids.isdisjoint(route_ids)
    assert all(route_id not in state.index._route_cells
               for route_id in route_ids)
    # no canonical-frame oracle residue
    oracle_route_ids = {entry[3]
                        for oracle in state.oracles.oracles.values()
                        for entry in (*oracle.h, *oracle.v)}
    assert oracle_route_ids.isdisjoint(route_ids)

    for route_id in route_ids:
        state.add(saved[route_id])
    assert len(state.index) == BASE_Z2_ROUTED
    # index state is bit-identical to a freshly built index of the same layout
    fresh = new_index(state.cfg)
    for route_id, result in state.accepted.items():
        fresh.add(route_id, result.prepared)
    assert index_cells_signature(state.index) == cells_before
    assert index_cells_signature(state.index) == index_cells_signature(fresh)
    # oracle recovery: exact same canonical occupancy lists
    assert oracle_signature(state) == oracles_before
    for route_id in route_ids:
        evaluation = state.index.evaluate(state.accepted[route_id].prepared,
                                          exclude=[route_id])
        assert evaluation.valid is True
        assert evaluation.reason is None
    assert_index_has_no_duplicate_entries(state.index)


# ---------------------------------------------------------------------------
# test 3: candidate de-dupe never removes a genuinely different legal track
# ---------------------------------------------------------------------------
class _FakeFrame:
    """Minimal adjacent frame interface used by the candidate builders."""

    def __init__(self, sx, qy):
        self.p = (float(sx), 0.0)
        self.q = (150.0, float(qy))
        self.qy = float(qy)
        self.kind = 'adjacent'
        self.source_side = 'S'
        self.target_side = 'E'


class _FakeOracle:
    """Zero-occupancy oracle: ranking only, never affects the geometry."""

    def h_parallel(self, *_args):
        return 0.0

    def v_parallel(self, *_args):
        return 0.0

    def h_crossings(self, *_args):
        return 0.0

    def v_crossings(self, *_args):
        return 0.0


def _moves_spec(family, moves):
    return dict(family=family, params={}, moves=list(moves), builder='moves')


def test_3_candidate_dedupe_keeps_distinct_geometry():
    radius = fslw_config.RADIUS_MM
    board = fslw_config.BOARD_MM
    sx, qy = 10.0, 45.0
    frame = _FakeFrame(sx, qy)
    oracle = _FakeOracle()

    # rigid single-L: up qy-R, quarter arc, straight into q
    rigid_l = _moves_spec('L', [('L', qy - radius), ('Q', -1),
                                ('L', board - sx - radius)])
    # byte-identical geometry under a different spec/family label
    duplicate_l = _moves_spec('L_COPY', [('L', qy - radius), ('Q', -1),
                                         ('L', board - sx - radius)])
    # genuinely different legal D56 track: early quarter turn + short-S level shift
    y0 = 41.0
    shift = qy - y0
    theta = math.acos(1.0 - abs(shift) / (2.0 * radius))
    advance = 2.0 * radius * math.sin(theta)
    turn_s = _moves_spec('TURN_S', [('L', y0 - radius), ('Q', -1),
                                    ('S', shift),
                                    ('L', board - (sx + radius) - advance)])

    candidates = list(candext.candidates_from_specs(
        frame, [rigid_l, duplicate_l, turn_s], oracle))
    # two distinct geometries survive, the duplicate is removed
    assert len(candidates) == 2, (
        f'dedupe kept {len(candidates)} candidates: '
        f'{[candidate["family"] for candidate in candidates]}')
    families = {candidate['family'] for candidate in candidates}
    assert families == {'L', 'TURN_S'}
    signatures = {candext._dedupe_signature(candidate['primitives'])  # noqa: SLF001
                  for candidate in candidates}
    assert len(signatures) == 2
    # both are real legal D56 chains that end exactly at the target port
    for candidate in candidates:
        primitives = candidate['primitives']
        assert primitives
        end = primitives[-1]['p1']
        assert end[0] == pytest.approx(board)
        assert end[1] == pytest.approx(qy)
        for primitive in primitives:
            assert primitive['kind'] in ('line', 'arc')
            if primitive['kind'] == 'arc':
                # only the fixed R=40 mm quarter arcs / short-S arcs are legal
                assert primitive['radius'] == pytest.approx(radius)
            else:  # straight segments must be axis aligned
                p0, p1 = primitive['p0'], primitive['p1']
                horizontal = abs(p0[1] - p1[1]) <= 1e-9
                vertical = abs(p0[0] - p1[0]) <= 1e-9
                assert horizontal != vertical, (p0, p1)


# ---------------------------------------------------------------------------
# test 4: failed R&R transaction rolls back completely
# ---------------------------------------------------------------------------
def test_4_rr_failed_transaction_rolls_back_completely():
    state = base_z2_state()
    accepted_ids = sorted(state.accepted)
    failed_ids = sorted(state.failed)
    assert accepted_ids and failed_ids
    target = failed_ids[0]
    keep = accepted_ids[0]
    other = accepted_ids[1]
    snapshot = state_signature(state)

    # (a) illegal placement: the target reuses the geometry of an accepted route
    assert state.index.evaluate(state.accepted[other].prepared).valid is False
    illegal = {
        'transaction': {'target': target, 'ripped': [], 'label': 'rollback/illegal'},
        'ripped': [],
        'placed': {target: {'primitives': state.accepted[other].primitives,
                            'family': None, 'params': {}}},
    }
    assert rr.commit_result(state, illegal, log=silent) is False
    assert state_signature(state) == snapshot

    # (b) net_gain <= 0: rip one route and place its own geometry as the target
    #     -> the routed count would not increase, so everything must roll back
    assert state.index.evaluate(state.accepted[keep].prepared,
                                exclude=[keep]).valid is True
    zero_gain = {
        'transaction': {'target': target, 'ripped': [keep],
                        'label': 'rollback/zero-gain'},
        'ripped': [keep],
        'placed': {target: {'primitives': state.accepted[keep].primitives,
                            'family': None, 'params': {}}},
    }
    assert rr.commit_result(state, zero_gain, log=silent) is False
    assert len(state.accepted) == BASE_Z2_ROUTED
    assert keep in state.accepted and target not in state.accepted
    assert state_signature(state) == snapshot

    # (c) target missing from the proposal -> immediate rejection
    assert rr.commit_result(state, {
        'transaction': {'target': target, 'ripped': [], 'label': 'rollback/missing'},
        'ripped': [], 'placed': {}}, log=silent) is False
    assert state_signature(state) == snapshot


# ---------------------------------------------------------------------------
# test 5: a transaction never places the same connection twice
# ---------------------------------------------------------------------------
def test_5_transaction_never_places_one_connection_twice():
    state, chosen_ids, _payload = small_layout()
    pending = [route['route_id'] for route in state.routes
               if route['route_id'] not in state.accepted]
    target = pending[0]
    ripped = chosen_ids[:2]
    transaction = {'target': target, 'ripped': ripped, 'size': len(ripped),
                   'reinsert_order': 'ripped_first', 'label': 'test/k2'}
    payload = {
        'dump': state.dump(),
        'transaction': transaction,
        'budget': 60,
        'reinsert_budget': 60,
        'max_evals_per_transaction': 600,
        'transaction_seconds': 20.0,
        'use_expanded': False,
        'seed': 1,
        'cfg': state.cfg,
    }
    state_before = list(state.accepted)
    result = rr.execute_transaction(payload)
    # executing a transaction on a private copy never touches the live layout
    assert list(state.accepted) == state_before

    placed = result['placed']
    assert len(placed) == len(set(placed))
    assert set(placed) <= {target} | set(result['ripped'])
    assert len(result['ripped']) == len(set(result['ripped']))
    assert result['final_count'] == (result['base_count']
                                     - len(result['ripped']) + len(placed))
    assert result['net_gain'] == (result['final_count']
                                  - result['base_count'])
    assert result['base_count'] == len(chosen_ids)

    before = len(state.accepted)
    committed = rr.commit_result(state, result, log=silent)
    if committed:
        assert len(state.accepted) == before + result['net_gain']
        assert set(result['placed']) <= set(state.accepted)
    else:
        assert len(state.accepted) == before
    assert len(state.index) == len(state.accepted)
    assert_index_has_no_duplicate_entries(state.index)
    assert state.verify()['audit_passed'] is True


# ---------------------------------------------------------------------------
# test 6: commit_result only reports an improvement on strict growth
# ---------------------------------------------------------------------------
def test_6_commit_result_only_returns_true_on_strict_growth():
    state = base_z2_state()
    target = sorted(state.failed)[0]
    line = free_synthetic_line(state)
    growth = {
        'transaction': {'target': target, 'ripped': [],
                        'label': 'growth/positive'},
        'ripped': [],
        'placed': {target: {'primitives': line, 'family': 'test',
                            'params': {}}},
    }
    before = len(state.accepted)
    assert rr.commit_result(state, growth, log=silent) is True
    assert len(state.accepted) == before + 1
    assert target in state.accepted
    assert target not in state.failed
    assert len(state.index) == len(state.accepted)
    assert_index_has_no_duplicate_entries(state.index)

    # zero-gain transaction: rip one, place its own geometry for the target
    next_target = sorted(state.failed)[0]
    keep = sorted(state.accepted)[0]
    assert state.index.evaluate(state.accepted[keep].prepared,
                                exclude=[keep]).valid is True
    count_before = len(state.accepted)
    zero = {
        'transaction': {'target': next_target, 'ripped': [keep],
                        'label': 'growth/zero'},
        'ripped': [keep],
        'placed': {next_target: {'primitives': state.accepted[keep].primitives,
                                 'family': None, 'params': {}}},
    }
    assert rr.commit_result(state, zero, log=silent) is False
    assert len(state.accepted) == count_before
    assert keep in state.accepted
    assert next_target not in state.accepted

    # invalid placement: the target geometry overlaps an accepted route
    invalid = {
        'transaction': {'target': next_target, 'ripped': [],
                        'label': 'growth/invalid'},
        'ripped': [],
        'placed': {next_target: {
            'primitives': state.accepted[keep].primitives,
            'family': None, 'params': {}}},
    }
    assert rr.commit_result(state, invalid, log=silent) is False
    assert len(state.accepted) == count_before


# ---------------------------------------------------------------------------
# test 7: checkpoint restores the real geometry of the historical best solution
# ---------------------------------------------------------------------------
def test_7_checkpoint_restores_real_geometry(base_z2, base_z2_verify, tmp_path):
    checkpoint = base_z2.save_checkpoint(tmp_path / 'best_z2.json',
                                         tag='regression')
    assert checkpoint.exists()
    stored = load_json(checkpoint)
    assert stored['schema'] == 'four_side_1024_v2opt_checkpoint_v1'
    assert len(stored['routed']) == BASE_Z2_ROUTED
    assert len(stored['failed']) == ROUTES_PER_PLANE - BASE_Z2_ROUTED

    restored = load_layout_from_checkpoint('V2', 'z2', checkpoint, log=silent)
    assert len(restored.accepted) == BASE_Z2_ROUTED
    assert set(restored.accepted) == set(base_z2.accepted)
    for route_id, result in base_z2.accepted.items():
        assert restored.accepted[route_id].primitives == result.primitives
        assert restored.accepted[route_id].length_mm == pytest.approx(
            result.length_mm)
        assert restored.accepted[route_id].bends == result.bends

    restored_info = restored.verify()
    # identical exact re-audit result as the original historical best solution
    assert restored_info == base_z2_verify
    assert restored_info['audit_passed'] is True
    assert restored_info['routed'] == BASE_Z2_ROUTED


# ---------------------------------------------------------------------------
# test 8: candidate budget never changes the physical constraints
# ---------------------------------------------------------------------------
def test_8_candidate_budget_does_not_change_physics():
    # the exact index configuration is physical and budget independent
    config = router_cfg()
    index_small = new_index(config)
    index_large = new_index(config)
    for attribute, expected in (('width', 0.05), ('gap', 0.03),
                                ('clearance', 0.08), ('min_angle_deg', 5.0)):
        assert getattr(index_small, attribute) == expected
        assert getattr(index_large, attribute) == expected
    assert config['min_radius_mm'] == fslw_config.RADIUS_MM == 40.0
    assert config['crossing_policy'] == 'strict'
    assert v2_config.BUDGET_LADDER == (200, 400, 800, 1600)

    state, _chosen_ids, _payload = small_layout(count=20, step=11)
    pending = [route['route_id'] for route in state.routes
               if route['route_id'] not in state.accepted]
    found = None
    for target in pending[:3]:
        frame = state.frames[target]
        spec_cache = (candext.adjacent_specs(frame, state.oracle_for(target))
                      if frame.kind == 'adjacent' else None)
        result_200, failure_200, stats_200 = search.attempt_route(
            state, target, budget=200, spec_cache=spec_cache)
        result_1600, failure_1600, stats_1600 = search.attempt_route(
            state, target, budget=1600, spec_cache=spec_cache)
        # the index keeps the frozen physical configuration during the search
        assert state.index.width == 0.05
        assert state.index.gap == 0.03
        assert state.index.clearance == 0.08
        assert stats_200['evaluated'] <= 200
        assert stats_1600['evaluated'] <= 1600
        if result_200 is not None:
            found = (target, result_200, result_1600, failure_1600)
            break
    assert found is not None, (
        'no legal candidate found on the sparse layout within the tested budgets')
    target, result_200, result_1600, _failure = found
    # a larger budget may not change an already-found legal candidate
    assert result_1600 is not None
    assert result_1600.primitives == result_200.primitives
    assert result_1600.prepared.length == pytest.approx(
        result_200.prepared.length)
    # and the found route passes the *frozen* single-route physical checks
    route = state.route_by_id[target]
    check = validate_fslw.check_route_primitives(
        result_200.primitives,
        state.endpoints[route['source_endpoint']],
        state.endpoints[route['target_endpoint']],
        width=fslw_config.WIDTH_MM, radius=fslw_config.RADIUS_MM,
        board=fslw_config.BOARD_MM, clearance=fslw_config.CLEARANCE_MM)
    assert check['passed'] is True, check['errors']
    assert check['length_mm'] == pytest.approx(result_200.length_mm)


# ---------------------------------------------------------------------------
# test 9: the final layout is re-auditable by the frozen authoritative validator
# ---------------------------------------------------------------------------
def test_9_final_layout_reaudited_by_frozen_validator():
    report = validate_fslw.build_report(
        routes_path=BASE_PLANES['z2'], policy='strict',
        expected_route_count=ROUTES_PER_PLANE)
    assert report['passed'] is True
    assert report['policy_used'] == 'strict'
    assert report['route_count'] == ROUTES_PER_PLANE
    assert report['routed_count'] == BASE_Z2_ROUTED
    assert report['failed_status_count'] == ROUTES_PER_PLANE - BASE_Z2_ROUTED
    assert report['d56_failed_count'] == 0
    assert report['d56_checked_count'] == BASE_Z2_ROUTED
    assert report['d56_passed_count'] == BASE_Z2_ROUTED
    assert report['violation_pair_count'] == 0
    assert report['errors'] == []
    assert report['endpoint_unchecked_count'] == 0
    assert report['structure']['checked'] is True
    assert report['process']['radius_mm'] == 40.0
    assert report['process']['centerline_clearance_mm'] == pytest.approx(0.08)
    assert report['crossing_count'] == BASE_Z2_CROSSINGS
    for field in ('spacing_violation_pairs', 'overlap_pairs', 'touch_pairs',
                  'crossing_window_overlap_pairs', 'double_cross_pairs',
                  'crossing_window_excessive_pairs', 'self_intersections',
                  'self_overlaps', 'self_spacing_violations',
                  'radius_violations', 'boundary_violations',
                  'diagonal_line_violations',
                  'free_or_short_s_arc_violations'):
        assert report[field] == 0, f'{field} = {report[field]}'


# ---------------------------------------------------------------------------
# extra contract test of the finalize module output (skipped until it is run)
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not FINAL_VALIDATION.exists(),
                    reason='final_validation.json not generated yet: run '
                           'four_side_1024/v2opt/finalize.py first')
def test_final_validation_base_entries():
    payload = load_json(FINAL_VALIDATION)
    assert payload['schema'].endswith('final_validation_v1')
    assert payload['topology'] == 'V2'
    z1 = payload['planes']['BASE/z1']
    z2 = payload['planes']['BASE/z2']
    for record, plane, routed in ((z1, 'z1', BASE_Z1_ROUTED),
                                  (z2, 'z2', BASE_Z2_ROUTED)):
        assert record['plane'] == plane
        assert record['passed'] is True
        assert record['validator_report']['passed'] is True
        assert record['validator_report']['routed_count'] == routed
        assert record['validator_report']['violations'][
            'violation_pair_count'] == 0
        assert record['identity']['passed'] is True
        assert record['identity']['record_count'] == ROUTES_PER_PLANE
        assert record['audit']['sha256'] == record['audit']['sha256'].lower()
        assert len(record['audit']['sha256']) == 64
    combined = payload['combined']['BASE']
    assert combined['passed'] is True
    assert combined['routed_total'] == BASE_Z1_ROUTED + BASE_Z2_ROUTED
    assert combined['same_plane_violation_total'] == 0
    assert payload['summary']['labels']['BASE']['all_passed'] is True
