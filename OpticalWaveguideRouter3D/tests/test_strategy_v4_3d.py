"""Step 17 (3D routing v4) tests: continued full-layout optimisation from a saved
3D terminal state with one explicit movement-permission switch (N/R).

Covered here:
- an already-elevated start state loads correctly and is validated;
- N and R share target order, generation, ranking, caches and acceptance and
  differ only in which victims may move;
- the structural generation-failure cache is judged on the CURRENTLY movable
  victims and never charges the budget or the attempt bound;
- the dynamic failure cache keeps the global-layout-version retry;
- the candidate-budget boundary only ever executes already fully accepted
  candidates;
- a relocation replaces the rise/elevated/fall structure and is length-accounted
  against the CURRENT route length, not the planar one;
- the incremental near-distance set equals a full rescan;
- candidates, full-acceptance passes and executed actions stay separate.
"""
from copy import deepcopy
from math import isclose
from src.models import Layer, Point3D
from src.geometry_3d import LineSegment3D, Route3D, CosineTransition3D
from src.geometry_3d_diagnostics import minimum_xy_run_for_radius
from src.sequential_elevation_3d import RouteView, pair_status
from src.three_layer_assignment_3d import LayerConfiguration
from src.layer_assignment_3d import build_elevation_candidate
from src.clearance_3d import analyze_route3d_clearance
from src.strategy_v2_3d import xy_projection_preserved
from src.strategy_v4_3d import (run_full_layout_v4, allow_relocation_for, elevation_structure,
    pair_state_distribution)


def config(n=3):
    return LayerConfiguration([Layer(i, float(i)) for i in range(n)], .1, 5.,
        'LINE_ONLY_FINITE_WINDOWS', 'EXPERIMENTAL_SYNTHETIC')


def L(a, b): return LineSegment3D(Point3D(*a), Point3D(*b))


def crossing_scenario():
    """Four planar routes: one solvable crossing, one clearance-only target."""
    routes = {0: Route3D(0, [L((-20, .5, 0), (20, .5, 0))]), 1: Route3D(1, [L((0, -20, 0), (0, 20, 0))]),
        2: Route3D(2, [L((30, -20, 0), (30, 20, 0))]), 3: Route3D(3, [L((10, 5, 0), (10, 15, 0))])}
    crossings = {(0, 1): [Point3D(0, .5, 0), Point3D(0, -10, 0)], (0, 2): [Point3D(10, 10, 0)]}
    return routes, crossings


def relocation_scenario():
    """Routes 0 and 1 are ALREADY elevated to layer 1 and cross on that layer, so
    they still collide. The only way to separate them is to re-place one of them
    on layer 2: N cannot (no movable route), R can (relocation)."""
    plan = {0: Route3D(0, [L((-50, 0, 0), (50, 0, 0))]), 1: Route3D(1, [L((0, -50, 0), (0, 50, 0))])}
    run1 = minimum_xy_run_for_radius(1., 5.)*(1 + 1e-6)/100.
    c0 = build_elevation_candidate(plan[0], (0, 1), [Point3D(0, 0, 0)], config(),
        (0, .01, .01 + run1), (0, .94, .99), target_layer_id=1)
    c1 = build_elevation_candidate(plan[1], (0, 1), [Point3D(0, 0, 0)], config(),
        (0, .40, .40 + run1), (0, .55, .60), target_layer_id=1)
    return {0: c0.route, 1: c1.route}, plan


def structural_scenario():
    """(0,1) is solvable, (2,3) can never generate a legal window, (4,5) is
    solvable and ranks after (2,3), so an accepted edit re-enables (2,3)."""
    routes = {0: Route3D(0, [L((-20, .5, 0), (20, .5, 0))]), 1: Route3D(1, [L((0, -20, 0), (0, 20, 0))]),
        2: Route3D(2, [L((30, -1, 0), (30, 1, 0))]), 3: Route3D(3, [L((29, 0, 0), (31, 0, 0))]),
        4: Route3D(4, [L((60, -20, 0), (60, 20, 0))]), 5: Route3D(5, [L((40, 5, 0), (80, 5, 0))])}
    crossings = {(0, 1): [Point3D(0, .5, 0)], (2, 3): [Point3D(30, 0, 0)], (4, 5): [Point3D(60, 5, 0)]}
    return routes, crossings


def half_failure_scenario():
    """Route 0 is 2 mm (never generates); route 1 is long and can be elevated."""
    return ({0: Route3D(0, [L((0, -1, 0), (0, 1, 0))]), 1: Route3D(1, [L((-20, 0, 0), (20, 0, 0))])},
        {(0, 1): [Point3D(0, 0, 0)]})


def run(routes, planar, mode, **kwargs):
    kwargs.setdefault('appended_candidate_budget', 400)
    kwargs.setdefault('max_targets', 10)
    return run_full_layout_v4(routes, planar, config(), mode=mode, **kwargs)


def full_rescan(routes):
    views = {i: RouteView.prepare(r) for i, r in routes.items()}
    pairs = set(); unknown = set()
    for a in sorted(routes):
        for b in sorted(routes):
            if a >= b: continue
            status = pair_status(views[a], views[b], .1)
            if status == 'COLLISION': pairs.add((a, b))
            elif status != 'CLEAR': unknown.add((a, b))
    return pairs, unknown


def candidate_rows(result):
    return [row for s in result['steps'] for va in s['victim_attempts'] for row in va['candidates']]


def timings(ledger):
    return {k: v for k, v in ledger.items() if 'seconds' in k}


def mode_free_steps(result):
    """Steps with the two mode-only fields removed, so the shared decision
    sequence can be compared across N and R."""
    return [{k: v for k, v in step.items() if k not in ('mode', 'allow_relocation')}
        for step in result['steps']]


def test_mode_switch_is_the_only_permission_difference():
    assert allow_relocation_for('N') is False and allow_relocation_for('R') is True
    try:
        allow_relocation_for('X')
        raise AssertionError('invalid mode accepted')
    except ValueError:
        pass
    # With no already-elevated route the two modes are identical everywhere.
    routes, crossings = crossing_scenario()
    n = run(routes, routes, 'N', saved_crossings=crossings)
    r = run(routes, routes, 'R', saved_crossings=crossings)
    assert mode_free_steps(n) == mode_free_steps(r)
    assert [s['mode'] for s in n['steps']] == ['N']*len(n['steps'])
    assert [s['mode'] for s in r['steps']] == ['R']*len(r['steps'])
    assert {k: v for k, v in n['ledger'].items()
        if k not in timings(n['ledger']) and k not in ('mode', 'allow_relocation')} == {
        k: v for k, v in r['ledger'].items()
        if k not in timings(r['ledger']) and k not in ('mode', 'allow_relocation')}
    assert n['ledger']['relocations'] == r['ledger']['relocations'] == 0
    assert n['ledger']['relocation_candidate_evaluations'] == 0


def test_elevated_start_state_loads_and_is_validated():
    start, plan = relocation_scenario()
    frozen = deepcopy(start)
    assert all(any(isinstance(p, CosineTransition3D) for p in r.primitives) for r in start.values())
    views = {i: RouteView.prepare(r) for i, r in start.items()}
    assert pair_status(views[0], views[1], .1) == 'COLLISION'
    result = run(start, plan, 'N')
    assert result['ledger']['initial_elevated_route_count'] == 2
    assert result['ledger']['initial_collision_pair_count'] == 1
    assert start == frozen
    # A start state that no longer projects onto the frozen planar route is rejected.
    broken = {0: Route3D(0, [L((-50, 1, 0), (50, 1, 0))]), 1: start[1]}
    try:
        run(broken, plan, 'N')
        raise AssertionError('XY-mismatched start state accepted')
    except ValueError as ex:
        assert 'INITIAL_XY_MISMATCH' in str(ex)


def test_N_cannot_move_but_R_relocates_the_same_target():
    start, plan = relocation_scenario()
    n = run(start, plan, 'N')
    r = run(start, plan, 'R')
    assert n['ledger']['no_movable_route_skip_events'] == 1
    assert n['steps'] == []
    assert n['ledger']['candidate_evaluations'] == 0
    assert n['ledger']['relocation_candidate_evaluations'] == 0
    assert n['ledger']['final_collision_pair_count'] == 1
    assert r['ledger']['relocation_candidate_evaluations'] > 0
    assert r['ledger']['relocations'] == 1
    assert r['ledger']['accepted_moves'] == 1
    assert r['ledger']['final_collision_pair_count'] == 0
    step = r['steps'][0]
    assert step['status'] == 'RELOCATED' and step['movement'] == 'RELOCATION'
    assert step['target_layer_id'] == 2
    assert r['ledger']['relocation_net_reduction'] == 1
    assert r['ledger']['first_elevation_net_reduction'] == 0


def test_relocation_replaces_structure_and_is_length_accounted_against_current():
    start, plan = relocation_scenario()
    r = run(start, plan, 'R')
    step = r['steps'][0]; moved = step['moved_route_id']
    before = start[moved].total_length(); after = r['routes'][moved].total_length()
    assert isclose(step['route_length_before_mm'], before)
    assert isclose(step['route_length_after_mm'], after)
    assert isclose(step['step_length_delta_mm'], after - before, abs_tol=1e-9)
    # The step delta is measured against the CURRENT elevated route, so it differs
    # from the change against the frozen planar route.
    planar_delta = after - plan[moved].total_length()
    assert abs(planar_delta - step['step_length_delta_mm']) > 1e-6
    # A relocation replaces the previous structure instead of stacking a second one.
    ok, reason = elevation_structure(r['routes'][moved])
    assert ok, reason
    transitions = [p for p in r['routes'][moved].primitives if isinstance(p, CosineTransition3D)]
    assert len(transitions) == 2
    assert transitions[0].start.z == 0. and transitions[0].end.z == 2.
    assert transitions[1].start.z == 2. and transitions[1].end.z == 0.
    assert step['structure_rebuilt_from_planar'] is True
    # Stage delta = sum of step deltas = terminal minus start, kept separate from
    # the extra length against the frozen planar routes.
    start_total = sum(x.total_length() for x in start.values())
    final_total = sum(x.total_length() for x in r['routes'].values())
    planar_total = sum(x.total_length() for x in plan.values())
    assert isclose(r['ledger']['stage_length_delta_mm'], final_total - start_total)
    assert isclose(r['ledger']['total_step_length_delta_mm'], step['step_length_delta_mm'])
    assert isclose(r['ledger']['final_extra_length_vs_planar_mm'], final_total - planar_total)
    assert isclose(r['ledger']['start_extra_length_vs_planar_mm'], start_total - planar_total)
    # Endpoints and the XY projection are preserved through the relocation.
    assert r['routes'][moved].start_point == plan[moved].start_point
    assert r['routes'][moved].end_point == plan[moved].end_point
    ok, reason = xy_projection_preserved(r['routes'][moved], plan[moved])
    assert ok, reason


def test_generation_cache_skips_without_charging_budget_or_attempts():
    routes, crossings = structural_scenario()
    off = run(routes, routes, 'N', saved_crossings=crossings, generation_failure_cache=False)
    on = run(routes, routes, 'N', saved_crossings=crossings, generation_failure_cache=True)
    assert [s['target_pair'] for s in off['steps']] == [(0, 1), (2, 3), (4, 5), (2, 3)]
    assert [s['target_pair'] for s in on['steps']] == [(0, 1), (2, 3), (4, 5)]
    assert on['ledger']['generation_skip_events'] == 1
    assert on['generation_skips'][0]['target_pair'] == (2, 3)
    assert on['ledger']['generation_skipped_target_count'] == 1
    # The skip consumes neither a candidate evaluation nor a formal attempt.
    assert on['ledger']['target_attempts'] == 3
    assert on['ledger']['candidate_evaluations'] == off['ledger']['candidate_evaluations']
    assert on['ledger']['accepted_moves'] == 2
    assert on['ledger']['final_collision_pair_count'] == off['ledger']['final_collision_pair_count'] == 1
    assert on['ledger']['generation_cache_zero_candidate_records'] == 2   # one record per victim


def test_generation_cache_is_judged_on_currently_movable_victims_only():
    # (a) One victim generates nothing, but the other CAN move: the target is
    # attempted normally instead of being skipped, and the one-sided zero
    # generation is recorded without becoming a skip.
    routes, crossings = half_failure_scenario()
    result = run(routes, routes, 'N', saved_crossings=crossings)
    assert len(result['steps']) == 1
    step = result['steps'][0]
    assert step['status'] == 'ELEVATED' and step['moved_route_id'] == 1
    assert result['ledger']['generation_skip_events'] == 0
    assert result['ledger']['zero_candidate_victim_attempts'] == 1
    assert result['ledger']['generation_cache_zero_candidate_records'] == 1
    # (b) A target with NO movable victim is a separate route-skip event in N: no
    # generation decision is taken at all and no attempt or evaluation is charged.
    start, plan = relocation_scenario()
    n = run(start, plan, 'N')
    assert n['ledger']['no_movable_route_skip_events'] == 1
    assert n['ledger']['no_movable_route_skipped_target_count'] == 1
    assert n['route_skips'][0]['reason'] == 'NO_MOVABLE_ROUTE_IN_MODE'
    assert n['ledger']['generation_skip_events'] == 0
    assert n['ledger']['generation_cache_records'] == 0
    assert n['ledger']['target_attempts'] == 0
    assert n['ledger']['candidate_evaluations'] == 0
    # (c) The same target under R has movable victims and is attempted.
    r = run(start, plan, 'R')
    assert r['ledger']['no_movable_route_skip_events'] == 0
    assert r['ledger']['target_attempts'] == 1
    assert r['ledger']['candidate_evaluations'] > 0
    # (d) A cached structural failure records which victims it was judged on.
    routes, crossings = structural_scenario()
    skip = run(routes, routes, 'N', saved_crossings=crossings)
    event = skip['generation_skips'][0]
    assert sorted(event['movable_victims']) == [2, 3]
    assert set(event['cached_generated_counts'].values()) == {0}


def test_dynamic_failure_cache_keeps_the_global_layout_version_retry():
    routes, crossings = structural_scenario()
    result = run(routes, routes, 'N', saved_crossings=crossings)
    pairs = [s['target_pair'] for s in result['steps']]
    repeated = [p for p in set(pairs) if pairs.count(p) > 1]
    # Dynamic failures (candidates exist, full acceptance fails) are retried after
    # any accepted edit anywhere, which is what the repeated (2,3) shows when the
    # generation cache is off; with the cache on the structural failure is skipped.
    assert repeated == []
    off = run(routes, routes, 'N', saved_crossings=crossings, generation_failure_cache=False)
    off_pairs = [s['target_pair'] for s in off['steps']]
    assert off_pairs.count((2, 3)) == 2
    # Every accepted edit bumps the layout version, so the failure cache entry
    # recorded before it can never suppress the target afterwards.
    versions = [s.get('layout_version_after') for s in result['steps'] if 'layout_version_after' in s]
    assert versions == sorted(versions) and versions == list(range(1, len(versions) + 1))


def test_candidate_budget_boundary_uses_only_fully_accepted_candidates():
    routes, crossings = crossing_scenario()
    for budget in (1, 5, 12, 30):
        result = run(routes, routes, 'N', appended_candidate_budget=budget, max_targets=10,
            saved_crossings=crossings)
        ledger = result['ledger']
        assert ledger['candidate_evaluations'] <= budget
        rows = candidate_rows(result)
        assert len(rows) == ledger['candidate_evaluations']
        assert ledger['generated_candidates'] >= ledger['candidate_evaluations']
        for step in result['steps']:
            if step['status'] in ('ELEVATED', 'RELOCATED'):
                victim = next(va for va in step['victim_attempts']
                    if va['route_id'] == step['moved_route_id'])
                chosen = victim['candidates'][step['selected_candidate_index']]
                assert chosen['status'] == 'ACCEPTED_FULL'
                assert step['full_acceptance_passes'] >= 1
    exhausted = run(routes, routes, 'N', appended_candidate_budget=1, max_targets=10,
        saved_crossings=crossings)
    assert exhausted['ledger']['candidate_evaluations'] == 1
    assert exhausted['ledger']['stop_reason'] in ('CANDIDATE_BUDGET_EXHAUSTED', 'NO_ELIGIBLE_TARGETS')


def test_incremental_near_distance_set_matches_a_full_rescan():
    for mode in ('N', 'R'):
        routes, crossings = crossing_scenario()
        before = {i: deepcopy(r) for i, r in routes.items()}
        result = run(routes, routes, mode, saved_crossings=crossings)
        initial_pairs, initial_unknown = full_rescan(before)
        final_pairs, final_unknown = full_rescan(result['routes'])
        assert set(map(tuple, result['initial_collision_pairs'])) == initial_pairs
        assert set(map(tuple, result['initial_unresolved_pairs'])) == initial_unknown
        assert set(map(tuple, result['final_collision_pairs'])) == final_pairs
        assert set(map(tuple, result['final_unresolved_pairs'])) == final_unknown
        assert result['ledger']['final_unresolved_pair_count'] == len(final_unknown)
        assert result['ledger']['final_collision_pair_count'] == len(final_pairs)
        assert result['curve'][-1]['collision_pair_count'] == len(final_pairs)
        # Every step strictly reduced the global pair count.
        for step in result['steps']:
            if step['status'] in ('ELEVATED', 'RELOCATED'):
                assert step['net_collision_reduction'] > 0
                assert (step['global_collision_pairs_before'] - step['global_collision_pairs_after']
                    == step['net_collision_reduction'])


def test_candidates_passes_and_executed_actions_stay_separate():
    start, plan = relocation_scenario()
    r = run(start, plan, 'R')
    ledger = r['ledger']
    assert ledger['generated_candidates'] >= ledger['candidate_evaluations']
    assert ledger['full_neighbor_checks'] <= ledger['candidate_evaluations']
    assert ledger['full_acceptance_passes'] >= ledger['executed_moves']
    assert len(candidate_rows(r)) == ledger['candidate_evaluations']
    assert ledger['executed_moves'] == ledger['first_elevations'] + ledger['relocations']
    assert ledger['executed_moves'] == ledger['accepted_moves']
    assert sum(s['full_acceptance_passes'] for s in r['steps']) >= ledger['executed_moves']
    # The relocation victim really was generated for, evaluated and selected.
    assert ledger['relocation_candidate_evaluations'] == ledger['candidate_evaluations']
    assert ledger['relocation_victim_attempts'] >= 1
    assert ledger['relocation_victims_selected'] == 1
    assert ledger['basic_rejection_reason_counts'].get('TARGET_NOT_CLEARED', 0) > 0


def test_pair_state_distribution_counts_the_three_route_states():
    pairs = {(0, 1), (0, 2), (1, 2), (2, 3)}
    distribution = pair_state_distribution(pairs, {2, 3})
    assert distribution == dict(both_routes_unelevated=1, single_route_elevated=2,
        both_routes_elevated=1, total=4)


def test_unresolved_pairs_are_never_treated_as_clear():
    # A pair whose analysis is not CLEAR must block a candidate that would keep it
    # unresolved: the full acceptance records it and refuses the strict decrease.
    routes, crossings = crossing_scenario()
    result = run(routes, routes, 'N', saved_crossings=crossings)
    for step in result['steps']:
        for va in step['victim_attempts']:
            for row in va['candidates']:
                if row['status'] == 'REJECTED_FULL':
                    assert row['full_reasons']
                    if row['unresolved_neighbor_ids']:
                        assert 'UNRESOLVED_NEIGHBOR' in row['full_reasons']
    assert result['ledger']['final_unresolved_pair_count'] == 0
