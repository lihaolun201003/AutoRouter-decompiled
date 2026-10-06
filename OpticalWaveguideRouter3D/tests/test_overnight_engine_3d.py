"""Targeted regression tests for the unified overnight engine
(src/overnight_engine_3d.py).

The engine generalises the verified step-17 driver (src/strategy_v4_3d.py) into
one loop whose scheduling, evaluation, coverage and extra mechanisms (A, F, H)
are pre-declared factors.  Every test below is deterministic and runs on a SMALL
synthetic fixture built from the real project geometry helpers
(three_layer_assignment_3d.LayerConfiguration +
layer_assignment_3d.build_elevation_candidate), never on the 512-route layout.

Covered here, one test each:
 1 stratified round robin: UU/UE/EE polled with equal weight, nothing starved;
 2 N and R share one target policy and differ only in movement permission;
 3 an executed move re-classifies the still-colliding targets;
 4 the static generation cache skips only structural zeros, and a layout-version
   change re-enables a dynamically failed target;
 5 the appended candidate budget is never exceeded and only a fully accepted
   candidate is executed;
 6 a relocation REPLACES the rise/elevated/fall structure (0 or 2 transitions);
 7 ledger stage_length_delta_mm equals the sum of executed step deltas;
 8 generated/offered/evaluated/full-checked/full-passed/executed stay separate
   and a NOT_EVALUATED row is never counted as a rejection;
 9 the E2 K prefix is a PER-TARGET total across both sides, never per side;
10 a K prefix without a winner is DEFERRED, never cached as all-failed;
11 idea A family round robin keeps the pool and K and changes only the offer;
12 idea B side reservation must guarantee relocation rows for the elevated
   victim (this one FAILS - see the report accompanying the run);
13 idea F exact dedup reports raw vs kept counts and removes bit-identical
   geometry only, never approximate equality;
14 idea H RETURN builds a zero-transition candidate, needs no min() over an
   empty transition set, runs only on a strict global decrease and removes the
   route from the elevated set;
15 E1/E2 still pick the winner by strategy_rank, never by the cheap estimate;
16 the cheap ordering estimate depends only on its documented inputs.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import replace
from functools import lru_cache
from math import fsum, isclose

from src.geometry_3d import CosineTransition3D, LineSegment3D, PathWindowTransition3D, Route3D
from src.geometry_3d_diagnostics import minimum_xy_run_for_radius
from src.layer_assignment_3d import build_elevation_candidate
from src.models import Layer, Point3D
from src.overnight_engine_3d import (MOVED_STATUSES, NE_BUDGET, NE_K_PREFIX, NOT_EVALUATED,
    SKIPPED_ELEVATED_STATUS_N, StrategySpec, _ReturnCandidate, _select_k_prefix,
    allow_relocation_for,
    cheap_candidate_score, elevation_state_class, elevation_structure, evaluate_return_candidate,
    family_key, geometry_fingerprint, run_strategy, transition_fragment_counts)
from src.strategy_v2_3d import (failure_cache_hit, generation_cache_hit, strategy_rank,
    window_rank_key)
from src.three_layer_assignment_3d import LayerConfiguration, candidate_families


# --------------------------------------------------------------------------
# fixtures and helpers
# --------------------------------------------------------------------------
def config(layers=3):
    return LayerConfiguration([Layer(i, float(i)) for i in range(layers)], .1, 5.,
        'LINE_ONLY_FINITE_WINDOWS', 'EXPERIMENTAL_SYNTHETIC')


def L(a, b): return LineSegment3D(Point3D(*a), Point3D(*b))


def elevate_at(planar, layer_z, cover_t, config_, *, before=.05, after=.05):
    """Legal single-elevation copy of a straight one-primitive route whose
    elevated window is centred on the route point at parameter cover_t (a window
    away from the collision point therefore leaves the collision in place)."""
    base = planar.primitives[0]
    span = base.length()
    width = minimum_xy_run_for_radius(float(layer_z), config_.required_radius_mm)*(1 + 1e-6)/span
    point = base.point_at(cover_t)
    return build_elevation_candidate(planar, (planar.route_id, -1), [Point3D(point.x, point.y, 0.)],
        config_, (0, cover_t - before - width, cover_t - before),
        (0, cover_t + after, cover_t + after + width), target_layer_id=int(layer_z)).route


def pair_routes(rid_h, rid_v, cy=0., half=20., kind='UU', config_=None):
    """One isolated crossing: horizontal at y=cy, vertical at x=0.  kind selects
    the scheduler state class the engine will see (UU / UE / EE)."""
    config_ = config_ or config()
    plan = {rid_h: Route3D(rid_h, [L((-half, cy, 0.), (half, cy, 0.))]),
            rid_v: Route3D(rid_v, [L((0., cy - half, 0.), (0., cy + half, 0.))])}
    if kind == 'UU':
        routes = dict(plan)
    elif kind == 'UE':
        routes = {rid_h: plan[rid_h], rid_v: elevate_at(plan[rid_v], 1, .8, config_)}
    elif kind == 'EE':
        routes = {rid_h: elevate_at(plan[rid_h], 1, .5, config_),
                  rid_v: elevate_at(plan[rid_v], 1, .5, config_)}
    else:
        raise ValueError(kind)
    return routes, plan


def state_class_layout():
    """Six isolated crossings, two per state class, 50 mm apart."""
    routes = {}; planar = {}
    for k, kind in enumerate(('UU', 'UE', 'EE', 'UU', 'UE', 'EE')):
        r, p = pair_routes(2*k, 2*k + 1, 50.*k, kind=kind)
        routes.update(r); planar.update(p)
    return routes, planar


def crossed_pair_layout():
    """The smallest solvable target: two planar routes crossing once."""
    routes, planar = pair_routes(0, 1)
    return dict(routes), planar


def elevated_victim_layout():
    """UE target: route 0 is already elevated (window far from the crossing, so
    the crossing itself stays on layer 0) and route 1 is a short planar victim."""
    cfg = config()
    planar = {0: Route3D(0, [L((-100, 0, 0), (100, 0, 0))]),
              1: Route3D(1, [L((0, -10, 0), (0, 10, 0))])}
    return {0: elevate_at(planar[0], 1, .8, cfg), 1: planar[1]}, planar


def elevated_crossing_layout():
    """EE target: both routes are elevated to layer 1 across their one crossing,
    so they still collide (on layer 1) and each of them can be relocated."""
    cfg = config()
    planar = {0: Route3D(0, [L((-20, 0, 0), (20, 0, 0))]),
              1: Route3D(1, [L((0, -20, 0), (0, 20, 0))])}
    return {0: elevate_at(planar[0], 1, .5, cfg), 1: elevate_at(planar[1], 1, .5, cfg)}, planar


def shared_route_layout():
    """(0,1) is a crossing that route 0 can solve, (0,2) is a second crossing of
    route 0 that lies in the 0.1 mm tail no generated window can ever cover, so
    it stays colliding and must be RE-CLASSIFIED after route 0 is elevated."""
    planar = {0: Route3D(0, [L((-50, 0, 0), (50, 0, 0))]),
              1: Route3D(1, [L((40, -1, 0), (40, 1, 0))]),
              2: Route3D(2, [L((49.95, -10, 0), (49.95, 10, 0))])}
    return dict(planar), planar


def deferred_prefix_layout():
    """An EE target with far more candidates than the K prefix can hold, plus an
    independent solvable UU target that moves afterwards."""
    routes = {}; planar = {}
    for rid_h, rid_v, cy, kind in ((0, 1, 0., 'EE'), (2, 3, 50., 'UU')):
        r, p = pair_routes(rid_h, rid_v, cy, kind=kind)
        routes.update(r); planar.update(p)
    return routes, planar


def blocked_relocation_layout():
    """Two-layer configuration: (0,1) is an EE collision relocation can never
    solve (there is no layer 2), (2,3) is a solvable planar crossing."""
    two = config(2)
    routes = {}; planar = {}
    for rid_h, rid_v, cy, kind in ((0, 1, 0., 'EE'), (2, 3, 50., 'UU')):
        r, p = pair_routes(rid_h, rid_v, cy, kind=kind, config_=two)
        routes.update(r); planar.update(p)
    return routes, planar, two


def structural_layout():
    """(0,1) and (4,5) are solvable; (2,3) can never generate a legal transition
    window, so its zero is STRUCTURAL rather than dynamic."""
    planar = {0: Route3D(0, [L((-20, .5, 0), (20, .5, 0))]),
              1: Route3D(1, [L((0, -20, 0), (0, 20, 0))]),
              2: Route3D(2, [L((30, -1, 0), (30, 1, 0))]),
              3: Route3D(3, [L((29, 0, 0), (31, 0, 0))]),
              4: Route3D(4, [L((60, -20, 0), (60, 20, 0))]),
              5: Route3D(5, [L((40, 5, 0), (80, 5, 0))])}
    return dict(planar), planar


def self_identical_layout():
    """EE target whose elevated route 0 IS one of the candidates the engine will
    regenerate for it (same frozen planar route, same anchors, same slack)."""
    cfg = config()
    planar = {0: Route3D(0, [L((-20, 0, 0), (20, 0, 0))]),
              1: Route3D(1, [L((0, -20, 0), (0, 20, 0))])}
    generated, _failure = candidate_families(planar[0], (0, 1), [Point3D(0., 0., 0.)], cfg,
        window_slack_mm=1e-5)
    assert len(generated) == 18
    return {0: generated[0].route, 1: elevate_at(planar[1], 1, .5, cfg)}, planar


def run(routes, planar, *, mode='N', config_=None, spec=None, budget=4000,
        generation_failure_cache=True, saved_crossings=None):
    return run_strategy(routes, planar, config_ or config(), mode=mode,
        appended_candidate_budget=budget, spec=spec or StrategySpec('TEST'),
        saved_crossings=saved_crossings, generation_failure_cache=generation_failure_cache)


@lru_cache(maxsize=None)
def stratified_result():
    """The deterministic stratified run of the six-crossing layout.

    Tests 1, 6, 7 and 8 all assert on this exact run; it is computed once and is
    only ever read (run_strategy never mutates its inputs)."""
    routes, planar = state_class_layout()
    return run(routes, planar, mode='R', budget=5000,
        spec=StrategySpec('STRATIFIED', target_policy='STRATIFIED'))


def candidate_rows(result):
    return [row for s in result['steps'] for va in s['victim_attempts'] for row in va['candidates']]


def evaluated_rows(step):
    return [row for va in step['victim_attempts'] for row in va['candidates']
            if row['status'] != NOT_EVALUATED]


def moved_steps(result):
    return [s for s in result['steps'] if s['status'] in MOVED_STATUSES]


def selected_row(step):
    victim = next(va for va in step['victim_attempts'] if va['route_id'] == step['moved_route_id'])
    return next(entry for entry in victim['candidates']
                if entry['candidate_index'] == step['selected_candidate_index'])


def rank_of(entry):
    """strategy_v2_3d.strategy_rank as it is applied to a recorded step row."""
    candidate = type('RecordedCandidate', (), dict(
        elevated_length_mm=entry['elevated_length_mm'], layer_to=entry['target_layer_id'],
        rise_window=entry['rise_window'], fall_window=entry['fall_window']))()
    return strategy_rank(dict(candidate=candidate, victim_id=entry['victim_id'],
        net_collision_reduction=entry['net_collision_reduction'],
        new_collisions_created=entry['new_collisions_created'],
        step_length_delta_mm=entry['step_length_delta_mm'],
        transition_count=entry['transition_count']))


def cheap_of(step, entry):
    """cheap_candidate_score reconstructed from the recorded step fields only."""
    first, second = step['target_pair']
    other = second if entry['victim_id'] == first else first
    return (-step['victim_degrees'][str(other)], entry['extra_length_mm'],
            entry['elevated_length_mm'], entry['target_layer_id'], entry['rise_window'],
            entry['fall_window'], entry['victim_id'], entry['candidate_index'])


def transition_count(route):
    return sum(isinstance(p, CosineTransition3D) for p in route.primitives)


# --------------------------------------------------------------------------
# 1 stratified round robin
# --------------------------------------------------------------------------
def test_stratified_round_robin_polls_every_state_class_with_equal_weight():
    routes, planar = state_class_layout()
    result = stratified_result()
    steps = result['steps']
    # step n polls ring[(n % 3):], so UE, EE, UU are each polled first once per
    # three steps and no non-empty class can be starved.
    assert [s['elevation_state_class'] for s in steps] == ['UE', 'EE', 'UU', 'UE', 'EE', 'UU']
    assert [s['target_pair'] for s in steps] == [(2, 3), (4, 5), (0, 1), (8, 9), (10, 11), (6, 7)]
    assert result['ledger']['coverage']['elevation_state_class_attempts'] == {
        'UU': 2, 'UE': 2, 'EE': 2}
    assert result['ledger']['coverage']['elevation_state_class_moves'] == {
        'UU': 2, 'UE': 2, 'EE': 2}
    assert result['ledger']['accepted_moves'] == 6
    assert result['ledger']['final_collision_pair_count'] == 0
    # The ring - not the fixture - is what balances the classes: the legacy
    # policy on the very same layout starts from the highest-priority pair, which
    # is the first UU crossing, and never gives the UE class the first turn.
    legacy = run(routes, planar, mode='R', budget=5000,
        spec=StrategySpec('LEGACY', max_targets=1))
    assert legacy['ledger']['stop_reason'] == 'TARGET_LIMIT'
    assert legacy['steps'][0]['target_pair'] == (0, 1)
    assert legacy['steps'][0]['elevation_state_class'] == 'UU'
    assert steps[0]['elevation_state_class'] == 'UE'


# --------------------------------------------------------------------------
# 2 one target policy, movement permission only
# --------------------------------------------------------------------------
def test_n_and_r_share_the_target_policy_and_differ_only_in_movement_permission():
    assert allow_relocation_for('N') is False
    assert allow_relocation_for('R') is True
    try:
        allow_relocation_for('X')
        raise AssertionError('invalid mode accepted')
    except ValueError:
        pass
    routes, planar = elevated_victim_layout()
    n = run(routes, planar, mode='N', spec=StrategySpec('PERMISSION'))
    r = run(routes, planar, mode='R', spec=StrategySpec('PERMISSION'))
    assert len(n['steps']) == len(r['steps']) == 1
    n_step = n['steps'][0]; r_step = r['steps'][0]
    assert n_step['target_pair'] == r_step['target_pair'] == (0, 1)
    assert n_step['elevation_state_class'] == r_step['elevation_state_class'] == 'UE'
    assert n_step['victim_degrees'] == r_step['victim_degrees']
    assert n_step['victim_order'] == r_step['victim_order'] == [0, 1]
    assert n_step['allow_relocation'] is False and r_step['allow_relocation'] is True
    # N: the elevated victim is skipped with the declared status and is never
    # generated for, evaluated or charged.
    skipped = n_step['victim_attempts'][0]
    assert skipped['route_id'] == 0 and skipped['movement'] == 'RELOCATION'
    assert skipped['status'] == SKIPPED_ELEVATED_STATUS_N
    assert skipped['candidates'] == [] and 'generated_count' not in skipped
    assert n['ledger']['already_elevated_victim_skips'] == 1
    assert n['ledger']['relocation_candidate_evaluations'] == 0
    assert n_step['status'] == 'ELEVATED' and n_step['moved_route_id'] == 1
    # R: the very same victim is generated for and evaluated.
    evaluated_victim = r_step['victim_attempts'][0]
    assert evaluated_victim['route_id'] == 0
    assert evaluated_victim['movement'] == 'RELOCATION'
    assert evaluated_victim['status'] != SKIPPED_ELEVATED_STATUS_N
    assert evaluated_victim['generated_count'] == 18
    assert any(e['status'] != NOT_EVALUATED for e in evaluated_victim['candidates'])
    assert r['ledger']['already_elevated_victim_skips'] == 0
    assert r['ledger']['relocation_candidate_evaluations'] == 18
    assert r_step['status'] == 'RELOCATED' and r_step['moved_route_id'] == 0


# --------------------------------------------------------------------------
# 3 re-classification after a state change
# --------------------------------------------------------------------------
def test_target_state_class_is_recomputed_after_an_executed_move():
    routes, planar = shared_route_layout()
    result = run(routes, planar, mode='N', spec=StrategySpec('RECLASS'))
    steps = result['steps']
    assert len(steps) == 2
    first, second = steps
    assert first['target_pair'] == (0, 1) and first['elevation_state_class'] == 'UU'
    assert first['elevated_routes_before'] == []
    assert first['status'] == 'ELEVATED' and first['moved_route_id'] == 0
    # The second crossing of route 0 is still colliding but is now classified UE
    # because of the move that was just executed.
    assert second['target_pair'] == (0, 2)
    assert second['elevated_routes_before'] == [0]
    assert second['elevation_state_class'] == 'UE'
    assert 0 in result['elevated_route_ids']
    assert elevation_state_class((0, 2), set()) == 'UU'
    assert elevation_state_class((0, 2), {0}) == 'UE'
    assert elevation_state_class((0, 2), {0, 2}) == 'EE'
    assert elevation_state_class((0, 1), {0, 1}) == 'EE'


# --------------------------------------------------------------------------
# 4 caches do not over-skip
# --------------------------------------------------------------------------
def test_static_generation_cache_skips_only_structural_zeros():
    routes, planar = structural_layout()
    cached = run(routes, planar, mode='N', spec=StrategySpec('CACHE'))
    uncached = run(routes, planar, mode='N', spec=StrategySpec('CACHE'),
        generation_failure_cache=False)
    assert [s['target_pair'] for s in cached['steps']] == [(0, 1), (2, 3), (4, 5)]
    assert [s['target_pair'] for s in uncached['steps']] == [(0, 1), (2, 3), (4, 5), (2, 3)]
    ledger = cached['ledger']
    assert ledger['generation_skip_events'] == 1
    event = cached['generation_skips'][0]
    assert event['target_pair'] == (2, 3) and set(event['cached_generated_counts'].values()) == {0}
    assert event['movable_victims'] == [2, 3]
    assert [e['target_pair'] for e in cached['generation_skips']] == [(2, 3)]
    # Only the structural zero was skipped: the two targets whose generation
    # produced candidates were never treated as structural failures.
    assert ledger['generation_cache_zero_candidate_records'] == 2
    assert ledger['generation_cache_records'] == 6
    assert ledger['generation_cache_records'] > ledger['generation_cache_zero_candidate_records']
    assert cached['steps'][0]['status'] == 'ELEVATED'
    assert cached['steps'][1]['status'] == 'NO_CANDIDATES_GENERATED'
    assert cached['steps'][2]['status'] == 'ELEVATED'
    assert cached['ledger']['accepted_moves'] == 2
    # Direct evidence: the cache matches only a recorded ZERO under the exact
    # same generation-input key.
    key = ('generation', 'input', 'key')
    zero = {((0, 1), 0): dict(key=key, generated_count=0)}
    nonzero = {((0, 1), 0): dict(key=key, generated_count=3)}
    assert generation_cache_hit(zero, (0, 1), 0, key) is True
    assert generation_cache_hit(nonzero, (0, 1), 0, key) is False
    assert generation_cache_hit({((0, 1), 1): dict(key=key, generated_count=0)},
        (0, 1), 0, key) is False
    assert generation_cache_hit(zero, (0, 1), 0, 'other') is False


def test_dynamic_failure_cache_is_re_enabled_by_a_layout_version_change():
    routes, planar, two = blocked_relocation_layout()
    result = run(routes, planar, mode='R', config_=two, spec=StrategySpec('DYNAMIC'))
    assert [s['target_pair'] for s in result['steps']] == [(0, 1), (2, 3), (0, 1)]
    first, second, third = result['steps']
    assert first['status'] == 'ALL_CANDIDATES_REJECTED'
    assert first['generated_candidates'] > 0 and first['evaluated_candidates'] > 0
    assert second['status'] == 'ELEVATED' and second['layout_version_after'] == 1
    assert third['layout_version_before'] == 1 and third['status'] == 'ALL_CANDIDATES_REJECTED'
    ledger = result['ledger']
    assert ledger['failed_all_rejected'] == 2
    # The dynamic failure is a NON-ZERO generation record, so the static cache
    # must not skip it: it is re-attempted after the layout version changed.
    assert ledger['generation_skip_events'] == 0
    assert ledger['generation_cache_records'] == 4
    assert ledger['generation_cache_zero_candidate_records'] == 0
    assert failure_cache_hit({(0, 1): 0}, (0, 1), 0) is True
    assert failure_cache_hit({(0, 1): 0}, (0, 1), 1) is False


# --------------------------------------------------------------------------
# 5 candidate budget boundary
# --------------------------------------------------------------------------
def test_candidate_budget_is_never_exceeded_and_only_accepted_candidates_execute():
    routes, planar = crossed_pair_layout()
    for budget in (1, 2, 5, 12, 30):
        result = run(routes, planar, mode='N', spec=StrategySpec('BUDGET'), budget=budget)
        ledger = result['ledger']
        assert ledger['candidate_evaluations'] <= budget
        assert ledger['budget_used_up'] is (ledger['candidate_evaluations'] >= budget)
        assert ledger['executed_moves'] == len(moved_steps(result))
        for step in result['steps']:
            assert step['candidate_evaluations_after'] <= budget
            assert step['evaluated_candidates'] <= step['offered_candidates']
        for step in moved_steps(result):
            chosen = selected_row(step)
            assert chosen['status'] == 'ACCEPTED_FULL'
            assert chosen['full_reasons'] == []
            assert step['full_acceptance_passes'] >= 1
            assert step['net_collision_reduction'] > 0
        assert ledger['aborted_steps_that_still_executed_a_move'] == 0
    exhausted = run(routes, planar, mode='N', spec=StrategySpec('BUDGET'), budget=1)
    assert exhausted['ledger']['candidate_evaluations'] == 1
    assert exhausted['ledger']['stop_reason'] == 'CANDIDATE_BUDGET_EXHAUSTED'
    # A step whose evaluation loop hit the budget still only executes a candidate
    # that had already been fully accepted before the boundary was reached.
    for step in moved_steps(exhausted):
        assert selected_row(step)['status'] == 'ACCEPTED_FULL'


# --------------------------------------------------------------------------
# 6 relocation replaces the structure
# --------------------------------------------------------------------------
def test_relocation_replaces_the_structure_instead_of_stacking_it():
    routes, planar = state_class_layout()
    result = stratified_result()
    relocations = [s for s in moved_steps(result) if s['movement'] == 'RELOCATION']
    assert len(relocations) == 4
    for step in relocations:
        moved = step['moved_route_id']
        route = result['routes'][moved]
        ok, reason = elevation_structure(route)
        assert ok, reason
        assert transition_count(route) == 2
        assert step['transition_count'] == 2
        assert step['structure_rebuilt_from_planar'] is True
    for route in result['routes'].values():
        ok, reason = elevation_structure(route)
        assert ok, reason
        assert transition_count(route) in (0, 2)
    assert result['ledger']['final_transition_count'] == 2*result['ledger']['final_elevated_route_count']
    assert result['ledger']['final_transition_count'] == sum(
        transition_count(route) for route in result['routes'].values())
    # elevation_structure itself: exactly zero or one LOGICAL rise/fall pair.
    # v8 re-declared this test on the logical z-profile instead of the number of
    # transition primitives (a logical ramp may be split into several physical
    # fragments); a route with only one ramp is now rejected as incomplete
    # rather than by a primitive count, and a second ramp / a third level is
    # still rejected.
    planar_route = Route3D(0, [L((-10, 0, 0), (10, 0, 0))])
    assert elevation_structure(planar_route) == (True, None)
    assert elevation_structure(routes[0]) == (True, None)
    one_rise = Route3D(0, [L((-10, 0, 0), (0, 0, 0)),
        CosineTransition3D(Point3D(0, 0, 0), Point3D(5, 0, 1))])
    assert elevation_structure(one_rise) == (False, 'INCOMPLETE_RISE_OR_FALL')
    three = Route3D(0, [L((-5, 0, 0), (0, 0, 0)),
        CosineTransition3D(Point3D(0, 0, 0), Point3D(5, 0, 1)),
        LineSegment3D(Point3D(5, 0, 1), Point3D(10, 0, 1)),
        CosineTransition3D(Point3D(10, 0, 1), Point3D(15, 0, 2)),
        LineSegment3D(Point3D(15, 0, 2), Point3D(20, 0, 2)),
        CosineTransition3D(Point3D(20, 0, 2), Point3D(25, 0, 1))])
    assert elevation_structure(three) == (False, 'LAYER_COUNT_3')
    # One logical rise split into TWO consecutive transition primitives that
    # share the phase, then one fall split into two more: accepted, and the
    # counts separate logical ramps from physical fragments.
    up1 = PathWindowTransition3D((L((0, 0, 0), (5, 0, 0)),), 0., 0.5)
    up2 = PathWindowTransition3D((L((5, 0, 0), (10, 0, 0)),), 0.5, 1.)
    down1 = PathWindowTransition3D((L((12, 0, 0), (17, 0, 0)),), 1., 0.5)
    down2 = PathWindowTransition3D((L((17, 0, 0), (22, 0, 0)),), 0.5, 0.)
    fragmented = Route3D(0, [L((-3, 0, 0), (0, 0, 0)), up1, up2,
        L((10, 0, 1), (12, 0, 1)), down1, down2, L((22, 0, 0), (25, 0, 0))])
    assert elevation_structure(fragmented) == (True, None)
    assert transition_fragment_counts(fragmented) == (2, 4)
    raised_without_transition = Route3D(0, [L((0, 0, 1), (10, 0, 1))])
    assert elevation_structure(raised_without_transition) == (False,
        'NONZERO_LAYER_WITHOUT_TRANSITION')


# --------------------------------------------------------------------------
# 7 length accounting
# --------------------------------------------------------------------------
def test_stage_length_delta_equals_the_sum_of_executed_step_deltas():
    routes, planar = state_class_layout()
    frozen = deepcopy(routes)
    initial_total = sum(r.total_length() for r in routes.values())
    result = stratified_result()
    assert routes == frozen
    moves = moved_steps(result)
    assert len(moves) == 6
    step_total = fsum(s['step_length_delta_mm'] for s in moves)
    ledger = result['ledger']
    final_total = sum(r.total_length() for r in result['routes'].values())
    assert isclose(ledger['stage_length_delta_mm'], step_total, abs_tol=1e-9)
    assert isclose(ledger['total_step_length_delta_mm'], step_total, abs_tol=1e-9)
    assert isclose(ledger['initial_total_length_mm'], initial_total, abs_tol=1e-9)
    assert isclose(ledger['final_total_length_mm'], final_total, abs_tol=1e-9)
    assert isclose(ledger['stage_length_delta_mm'], final_total - initial_total, abs_tol=1e-9)
    per_move_total = fsum(s['step_length_delta_mm'] for s in moves)
    by_kind = fsum(ledger[key] for key in ('first_elevation_step_length_delta_mm',
        'relocation_step_length_delta_mm', 'return_step_length_delta_mm'))
    assert isclose(by_kind, per_move_total, abs_tol=1e-9)
    for step in moves:
        assert isclose(step['step_length_delta_mm'],
            step['route_length_after_mm'] - step['route_length_before_mm'], abs_tol=1e-9)
        assert isclose(step['route_length_after_mm'],
            result['routes'][step['moved_route_id']].total_length(), abs_tol=1e-9)


# --------------------------------------------------------------------------
# 8 stage counts stay separate
# --------------------------------------------------------------------------
def test_stage_counts_stay_distinct_and_unevaluated_rows_are_never_rejections():
    exhausted = stratified_result()
    rows = candidate_rows(exhausted)
    ledger = exhausted['ledger']
    evaluated = [r for r in rows if r['status'] != NOT_EVALUATED]
    assert len(evaluated) == ledger['candidate_evaluations']
    assert ledger['generated_candidates'] >= ledger['candidate_evaluations']
    assert ledger['candidate_evaluations'] >= ledger['full_neighbor_checks']
    assert ledger['full_neighbor_checks'] >= ledger['full_acceptance_passes']
    assert ledger['full_acceptance_passes'] >= ledger['executed_moves']
    assert ledger['executed_moves'] == ledger['accepted_moves'] == len(moved_steps(exhausted))
    assert ledger['not_evaluated_candidates'] == 0
    # Rejection counters are recomputable from the rows and never include a
    # NOT_EVALUATED row.
    basic = Counter(reason for row in rows if row['status'] == 'BASIC_REJECTED'
                    for reason in (row.get('basic_reasons') or []))
    full = Counter(reason for row in rows if row['status'] == 'REJECTED_FULL'
                   for reason in (row.get('full_reasons') or []))
    assert ledger['basic_rejection_reason_counts'] == dict(basic)
    assert ledger['full_rejection_reason_counts'] == dict(full)
    # E2 with a K prefix: offered, evaluated and truncated are three different
    # numbers, and the truncated rows are NOT_EVALUATED rows of their own line.
    deferred_layout, deep_planar = deferred_prefix_layout()
    deferred = run(deferred_layout, deep_planar, mode='R', budget=5000,
        spec=StrategySpec('E2', evaluation_policy='E2_ORDERED_K16', k_per_target=4))
    first = deferred['steps'][0]
    assert first['generated_candidates'] == 36
    assert first['offered_candidates'] == 4
    assert first['evaluated_candidates'] == 4
    assert first['k_prefix_truncated_candidates'] == 32
    assert first['not_evaluated_candidates'] == 32
    assert first['full_acceptance_passes'] == 0
    assert first['status'] == 'PREFIX_EVALUATED_NO_WINNER_DEFERRED'
    assert deferred['ledger']['generated_candidates'] > deferred['ledger']['candidate_evaluations']
    assert deferred['ledger']['not_evaluated_candidates'] == deferred['ledger']['not_evaluated_by_k_prefix']
    not_evaluated = [r for r in candidate_rows(deferred) if r['status'] == NOT_EVALUATED]
    assert len(not_evaluated) == deferred['ledger']['not_evaluated_candidates']
    assert all(r['basic_status'] is None and r['basic_reasons'] is None and 'full_reasons' not in r
               for r in not_evaluated)
    assert all(r['status'] != NOT_EVALUATED for r in
               [row for row in candidate_rows(deferred)
                if row['status'] in ('BASIC_REJECTED', 'REJECTED_FULL')])


# --------------------------------------------------------------------------
# 9 E2 K prefix is per target
# --------------------------------------------------------------------------
def test_e2_k_prefix_is_a_per_target_total_across_both_sides():
    routes, planar = deferred_prefix_layout()
    spec = StrategySpec('E2', evaluation_policy='E2_ORDERED_K16', k_per_target=4)
    result = run(routes, planar, mode='R', spec=spec, budget=5000)
    first = result['steps'][0]
    assert first['target_pair'] == (0, 1)
    assert [va['generated_count'] for va in first['victim_attempts']] == [18, 18]
    assert first['generated_candidates'] == 36
    # One shared quota for the whole target: 4, not 4 per side.
    assert first['offered_candidates'] == spec.k_per_target
    assert first['offered_candidates'] != 4*len(first['target_pair'])
    assert first['offered_candidates'] != 2*spec.k_per_target
    assert first['k_prefix_truncated_candidates'] == 32
    offered_per_victim = []
    for va in first['victim_attempts']:
        offered = [r for r in va['candidates']
                   if r['status'] != NOT_EVALUATED or r.get('not_evaluated_reason') == NE_BUDGET]
        offered_per_victim.append(len(offered))
    assert sum(offered_per_victim) == first['offered_candidates'] == spec.k_per_target
    assert all(count <= spec.k_per_target for count in offered_per_victim)
    for step in result['steps']:
        assert step['offered_candidates'] <= spec.k_per_target
    # The prefix never lets the run pass the appended budget either.
    small = run(routes, planar, mode='R', spec=spec, budget=2)
    assert small['ledger']['candidate_evaluations'] <= 2
    assert all(step['offered_candidates'] <= spec.k_per_target for step in small['steps'])
    assert small['ledger']['stop_reason'] == 'CANDIDATE_BUDGET_EXHAUSTED'


# --------------------------------------------------------------------------
# 10 deferred prefix
# --------------------------------------------------------------------------
def test_e2_prefix_without_a_winner_is_deferred_and_not_cached_as_all_failed():
    routes, planar = deferred_prefix_layout()
    spec = StrategySpec('E2', evaluation_policy='E2_ORDERED_K16', k_per_target=4)
    result = run(routes, planar, mode='R', spec=spec, budget=5000)
    assert [s['target_pair'] for s in result['steps']] == [(0, 1), (2, 3), (0, 1)]
    first = result['steps'][0]
    assert first['status'] == 'PREFIX_EVALUATED_NO_WINNER_DEFERRED'
    assert first['prefix_evaluated_no_winner_deferred'] is True
    assert first['deferred_target_retriable'] is True
    unevaluated = [r for va in first['victim_attempts'] for r in va['candidates']
                   if r['status'] == NOT_EVALUATED]
    assert len(unevaluated) == 32
    assert {r['not_evaluated_reason'] for r in unevaluated} == {NE_K_PREFIX}
    ledger = result['ledger']
    assert ledger['deferred_prefix_no_winner'] == 2
    assert ledger['deferred_target_entries'] == 1
    assert ledger['failed_all_rejected'] == 0
    assert ledger['failed_no_winner'] == 0
    assert ledger['not_evaluated_by_k_prefix'] == 96
    assert ledger['not_evaluated_by_budget'] == 0
    assert all(s['status'] != 'ALL_CANDIDATES_REJECTED' for s in result['steps'])
    # NOT written into the all-failed cache: the target is attempted again once
    # another accepted move bumped the layout version.
    assert result['steps'][2]['layout_version_before'] == 1
    assert result['steps'][0]['layout_version_before'] == 0
    assert result['steps'][1]['status'] == 'ELEVATED'
    assert result['steps'][2]['evaluated_candidates'] == 4


# --------------------------------------------------------------------------
# 11 idea A family round robin
# --------------------------------------------------------------------------
def test_family_round_robin_keeps_the_pool_and_k_and_changes_only_the_offer():
    routes, planar = crossed_pair_layout()
    base = dict(evaluation_policy='E2_ORDERED_K16', k_per_target=4)
    unified = run(routes, planar, mode='N', spec=StrategySpec('UNIFIED', **base), budget=5000)
    family = run(routes, planar, mode='N',
        spec=StrategySpec('FAMILY', family_round_robin=True, **base), budget=5000)
    assert [s['generated_candidates'] for s in unified['steps']] == [36]
    assert [s['generated_candidates'] for s in family['steps']] == [36]
    assert [s['offered_candidates'] for s in unified['steps']] == [4]
    assert [s['offered_candidates'] for s in family['steps']] == [4]
    assert [s['k_prefix_truncated_candidates'] for s in unified['steps']] == [32]
    assert [s['k_prefix_truncated_candidates'] for s in family['steps']] == [32]
    assert [va['generated_count'] for va in unified['steps'][0]['victim_attempts']] == \
        [va['generated_count'] for va in family['steps'][0]['victim_attempts']] == [18, 18]
    unified_offer = [(e['victim_id'], e['candidate_index'], tuple(e['candidate_family']))
                     for e in evaluated_rows(unified['steps'][0])]
    family_offer = [(e['victim_id'], e['candidate_index'], tuple(e['candidate_family']))
                    for e in evaluated_rows(family['steps'][0])]
    assert len(unified_offer) == len(family_offer) == 4
    assert unified_offer != family_offer
    assert {entry[1] for entry in unified_offer} != {entry[1] for entry in family_offer}
    # The unified cheap order fills the whole prefix from one family, the family
    # round robin takes from both configured layers.
    assert {entry[2][0] for entry in unified_offer} == {1}
    assert {entry[2][0] for entry in family_offer} == {1, 2}
    assert len({entry[2] for entry in family_offer}) == 2
    # family_key is the documented (layer, rise primitive, fall primitive) key.
    generated, _ = candidate_families(planar[0], (0, 1), [Point3D(0., 0., 0.)], config(),
        window_slack_mm=1e-5)
    for candidate in generated:
        assert family_key(candidate) == (candidate.layer_to, candidate.rise_window[0],
            candidate.fall_window[0])
    assert {family_key(c) for c in generated} == {(1, 0, 0), (2, 0, 0)}


# --------------------------------------------------------------------------
# 12 idea B side reservation  (expected to FAIL: see the run report)
# --------------------------------------------------------------------------
def test_side_reserve_guarantees_relocation_rows_for_the_elevated_victim():
    routes, planar = elevated_victim_layout()
    spec = StrategySpec('SIDE_RESERVE', evaluation_policy='E2_ORDERED_K16',
        k_per_target=2, relocation_side_reserve=2)
    result = run(routes, planar, mode='R', spec=spec, budget=4000)
    step = result['steps'][0]
    elevated_victim = step['victim_attempts'][0]
    assert elevated_victim['route_id'] == 0
    assert elevated_victim['movement'] == 'RELOCATION'
    assert elevated_victim['generated_count'] >= spec.relocation_side_reserve
    # This assertion used to pin the DEFECT (every pooled row carried the uniform
    # historical action='ELEVATE', which is why the reservation matched nothing).
    # It now pins the FIX: each pooled row carries the victim's real movement, so
    # the elevated side is labelled RELOCATION and the planar side FIRST_ELEVATION.
    assert {e['action'] for e in elevated_victim['candidates']} == {'RELOCATION'}
    plan = {e['action'] for e in step['victim_attempts'][1]['candidates']}
    assert plan == {'FIRST_ELEVATION'}
    # Idea B declares that at least relocation_side_reserve slots are filled from
    # the elevated victim's own RELOCATION/RETURN candidates before the global
    # cheap order fills the rest.
    evaluated = [e for e in elevated_victim['candidates'] if e['status'] != NOT_EVALUATED]
    relocation_rows = [e for e in evaluated if e['movement'] == 'RELOCATION']
    planar_victim = step['victim_attempts'][1]
    planar_rows = [e for e in planar_victim['candidates'] if e['status'] != NOT_EVALUATED]
    assert len(relocation_rows) >= spec.relocation_side_reserve, (
        'idea B side reservation reserved no slot for the elevated victim: '
        'k_per_target=%d relocation_side_reserve=%d evaluated_relocation_rows=%d '
        'evaluated_first_elevation_rows=%d'
        % (spec.k_per_target, spec.relocation_side_reserve, len(relocation_rows),
           len(planar_rows)))
    assert step['offered_candidates'] == spec.k_per_target
    assert result['ledger']['relocation_candidate_evaluations'] >= spec.relocation_side_reserve


# --------------------------------------------------------------------------
# 13 idea F exact dedup
# --------------------------------------------------------------------------
def test_exact_dedup_removes_bit_identical_geometry_only_and_reports_raw_counts():
    routes, planar = self_identical_layout()
    result = run(routes, planar, mode='R', spec=StrategySpec('DEDUP', exact_dedup=True), budget=4000)
    step = result['steps'][0]
    victim = step['victim_attempts'][0]
    assert victim['raw_generated_count'] == 18
    assert victim['generated_count'] == 17
    assert victim['dedup_removed_identical_to_current'] == 1
    assert victim['dedup_removed_duplicates'] == 0
    assert victim['raw_generated_count'] == victim['generated_count'] + \
        victim['dedup_removed_identical_to_current'] + victim['dedup_removed_duplicates']
    ledger = result['ledger']
    assert ledger['dedup_removed_identical_to_current'] == 1
    assert ledger['dedup_removed_duplicates'] == 0
    # The per-step pool is post-dedup, the run ledger accumulates the RAW
    # generation count: both numbers are asserted explicitly instead of assumed.
    assert step['generated_candidates'] == 35
    assert ledger['generated_candidates'] == 36
    assert ledger['generated_candidates'] == sum(
        va['raw_generated_count'] for s in result['steps'] for va in s['victim_attempts'])
    # Fingerprints are exact: an identical copy is identical, a 1e-9 mm shift is
    # NOT (approximate equality must never be removed).
    base = Route3D(0, [L((-20, 0, 0), (20, 0, 0))])
    same = Route3D(0, [L((-20, 0, 0), (20, 0, 0))])
    shifted = Route3D(0, [L((-20 + 1e-9, 0, 0), (20, 0, 0))])
    assert geometry_fingerprint(base) == geometry_fingerprint(same)
    assert geometry_fingerprint(base) != geometry_fingerprint(shifted)
    delta = geometry_fingerprint(shifted)[0][1] - geometry_fingerprint(base)[0][1]
    assert delta != 0. and abs(delta - 1e-9) < 1e-15
    elevated_planar = planar[0]
    assert geometry_fingerprint(planar[0]) != geometry_fingerprint(routes[0])
    assert geometry_fingerprint(planar[0]) == geometry_fingerprint(deepcopy(elevated_planar))


# --------------------------------------------------------------------------
# 14 idea H RETURN
# --------------------------------------------------------------------------
def test_return_candidate_is_zero_transition_and_needs_no_min_over_an_empty_set():
    routes, planar = elevated_crossing_layout()
    original = routes[0]
    elevated_length = sum(p.length() for p in original.primitives
                          if p.start.z != 0. and p.end.z != 0.)
    returned = _ReturnCandidate(0, (0, 1), deepcopy(planar[0]), original.total_length(),
        elevated_length)
    assert returned.action == 'RETURN' and returned.is_return is True
    assert returned.layer_from == 0 and returned.layer_to == 0
    assert returned.delta_z == 0. and returned.transition_run_mm == 0.
    assert returned.rise_window == () and returned.fall_window == ()
    assert returned.target_crossing == ()
    assert transition_count(returned.route) == 0
    assert returned.new_length_mm == planar[0].total_length()
    basic = evaluate_return_candidate(returned, original, routes[1], config())
    assert basic['status'] == 'ACCEPTED_TARGET_PAIR_ONLY'
    assert basic['reasons'] == []
    # No transitions at all: the radius requirement is recorded as vacuous
    # instead of taking min() over an empty set (which would raise).
    assert basic['minimum_radius_mm'] == float('inf')
    assert basic['zero_transition_radius_check'] == 'VACUOUS_NO_TRANSITION'
    assert basic['target_before']['status'] == 'COLLISION'
    assert basic['target_after']['status'] == 'CLEAR'
    assert basic['target_collision_removed'] is True
    assert basic['endpoint_invariant'] is True
    assert basic['local_validation_status'] == 'NOT_PERFORMED'


def test_return_runs_only_on_a_strict_global_decrease_and_leaves_the_elevated_set():
    routes, planar = elevated_crossing_layout()
    result = run(routes, planar, mode='R', spec=StrategySpec('RETURN', return_action=True),
        budget=4000)
    step = result['steps'][0]
    assert step['status'] == 'RETURNED_TO_PLANE'
    assert step['movement'] == 'RETURN' and step['action'] == 'RETURN'
    assert step['transition_count'] == 0
    assert step['net_collision_reduction'] > 0
    assert step['global_collision_pairs_before'] - step['global_collision_pairs_after'] == \
        step['net_collision_reduction']
    moved = step['moved_route_id']
    assert moved not in result['elevated_route_ids']
    assert result['returned_route_ids'] == [moved]
    assert transition_count(result['routes'][moved]) == 0
    ok, reason = elevation_structure(result['routes'][moved])
    assert ok, reason
    assert result['routes'][moved].start_point == planar[moved].start_point
    assert result['routes'][moved].end_point == planar[moved].end_point
    ledger = result['ledger']
    assert ledger['returns'] == 1 and ledger['accepted_moves'] == 1
    assert ledger['return_candidates_built'] >= 1
    assert ledger['return_candidate_evaluations'] > 0
    assert ledger['return_net_reduction'] > 0
    assert ledger['final_elevated_route_count'] == 1


# --------------------------------------------------------------------------
# 15 winner selection
# --------------------------------------------------------------------------
def test_winner_is_the_strategy_rank_minimum_not_the_cheap_estimate():
    routes, planar = elevated_victim_layout()
    specs = (StrategySpec('E1', evaluation_policy='E1_ORDERED_EXHAUSTIVE'),
             StrategySpec('E2', evaluation_policy='E2_ORDERED_K16', k_per_target=16))
    for spec in specs:
        result = run(routes, planar, mode='R', spec=spec, budget=4000)
        for step in moved_steps(result):
            accepted = [e for va in step['victim_attempts'] for e in va['candidates']
                        if e['status'] == 'ACCEPTED_FULL']
            assert accepted
            chosen = selected_row(step)
            assert rank_of(chosen) == min(rank_of(e) for e in accepted)
    # The fixture discriminates: the rank-best row is NOT the row the cheap
    # ordering estimate would have picked.
    result = run(routes, planar, mode='R',
        spec=StrategySpec('E1', evaluation_policy='E1_ORDERED_EXHAUSTIVE'), budget=4000)
    step = result['steps'][0]
    accepted = [e for va in step['victim_attempts'] for e in va['candidates']
                if e['status'] == 'ACCEPTED_FULL']
    chosen = selected_row(step)
    cheap_best = min(accepted, key=lambda e: cheap_of(step, e))
    assert (chosen['victim_id'], chosen['candidate_index']) != \
        (cheap_best['victim_id'], cheap_best['candidate_index'])
    assert rank_of(chosen) < rank_of(cheap_best)
    # With the whole pool evaluated, E0, E1 and E2 (large K) execute exactly the
    # same sequence: the evaluation order and the prefix never change the winner.
    def signature(spec):
        outcome = run(routes, planar, mode='R', spec=spec, budget=4000)
        return [(s['target_pair'], s.get('moved_route_id'), s.get('selected_candidate_index'),
                 s.get('action')) for s in outcome['steps']]
    assert signature(StrategySpec('E0')) == signature(specs[0]) == \
        signature(StrategySpec('E2_ALL', evaluation_policy='E2_ORDERED_K16', k_per_target=100000))


# --------------------------------------------------------------------------
# 16 cheap ordering estimate inputs
# --------------------------------------------------------------------------
def test_cheap_candidate_score_depends_only_on_its_documented_inputs():
    generated, _failure = candidate_families(Route3D(0, [L((-20, 0, 0), (20, 0, 0))]), (0, 1),
        [Point3D(0., 0., 0.)], config(), window_slack_mm=1e-5)
    assert len(generated) == 18
    first, second = generated[0], generated[1]
    degrees = {1: 3}
    score = cheap_candidate_score(0, 5, first, 1, degrees)
    # v8 re-declared the estimate to compare OLD and NEW windows in one pool:
    # the windows enter through the canonical 4-tuple (start primitive, start t,
    # end primitive, end t) and a declared window-kind rank follows layer_to.
    # For the historical line windows this is order-identical to before.
    assert score == (-3, first.extra_length_mm, first.elevated_length_mm, first.layer_to, 0,
        window_rank_key(first.rise_window), window_rank_key(first.fall_window), 0, 5)
    assert window_rank_key(first.rise_window) == (first.rise_window[0], first.rise_window[1],
        first.rise_window[0], first.rise_window[2])
    # Same declared fields, different route (and therefore a different true net
    # reduction): the estimate is bit-identical.
    twin = replace(first, route=second.route)
    assert twin.route is not first.route
    assert cheap_candidate_score(0, 5, twin, 1, degrees) == score
    # The only neighbour input is the other route's current conflict degree.
    assert cheap_candidate_score(0, 5, first, 1, {1: 9})[0] == -9
    assert cheap_candidate_score(0, 5, first, 1, {})[0] == 0
    # other_route_id only enters through degrees.get(other_route_id, 0).
    assert cheap_candidate_score(0, 5, first, 7, degrees) == (0,) + score[1:]
    assert cheap_candidate_score(11, 5, first, 1, degrees)[-2] == 11
    assert cheap_candidate_score(0, 13, first, 1, degrees)[-1] == 13
    # A duck-typed candidate exposing ONLY the documented fields is enough: no
    # acceptance row, no neighbour scan and no route is ever touched.
    documented = type('DocumentedCandidate', (), dict(extra_length_mm=1.5,
        elevated_length_mm=7.0, layer_to=2, rise_window=(0, .1, .2), fall_window=(0, .8, .9)))()
    # v8: the windows enter as canonical 4-tuples and a declared window-kind
    # rank follows layer_to; a duck-typed candidate that exposes only the
    # historical fields is still enough (window_kind defaults to the line kind).
    assert cheap_candidate_score(4, 6, documented, 1, {1: 2}) == (-2, 1.5, 7.0, 2, 0,
        (0, .1, 0, .2), (0, .8, 0, .9), 4, 6)

# --------------------------------------------------------------------------
# 12b idea B side reservation at the prefix level (unit contract)
# --------------------------------------------------------------------------
def test_select_k_prefix_reserves_relocation_rows_for_an_elevated_victim():
    """_select_k_prefix contract: with an elevated victim in the pool the returned
    prefix holds at least relocation_side_reserve RELOCATION rows, and the whole
    prefix still fits inside k_per_target."""
    reserve = StrategySpec('PREFIX_RESERVE', evaluation_policy='E2_ORDERED_K16',
        k_per_target=3, relocation_side_reserve=2)
    plain = StrategySpec('PREFIX_PLAIN', evaluation_policy='E2_ORDERED_K16',
        k_per_target=3, relocation_side_reserve=0)
    order = [0, 1]
    elevated = {0}
    movable = {0: dict(status='SELECTED'), 1: dict(status='SELECTED')}

    def row(victim, index, action):
        return dict(victim_id=victim, candidate_index=index, candidate=None, other=None,
                    action=action)

    # The global cheap order puts the planar victim's five rows first, so without
    # the reservation the elevated victim would be crowded out of the prefix.
    pool = [row(1, index, 'FIRST_ELEVATION') for index in range(5)] + \
        [row(0, index, 'RELOCATION') for index in range(2)]
    plain_prefix = _select_k_prefix(list(pool), plain, order, elevated, movable)
    assert [r['action'] for r in plain_prefix] == ['FIRST_ELEVATION']*3
    reserved = _select_k_prefix(list(pool), reserve, order, elevated, movable)
    assert len(reserved) <= reserve.k_per_target
    assert len(reserved) == reserve.k_per_target
    assert len({id(r) for r in reserved}) == len(reserved)
    assert sum(1 for r in reserved if r['action'] == 'RELOCATION') >= reserve.relocation_side_reserve
    assert {r['victim_id'] for r in reserved} == {0, 1}
    # A victim that N mode skipped is not reserved for: the plain prefix stands.
    skipped = {0: dict(status=SKIPPED_ELEVATED_STATUS_N), 1: dict(status='SELECTED')}
    assert [r['action'] for r in
            _select_k_prefix(list(pool), reserve, order, elevated, skipped)] == \
        ['FIRST_ELEVATION']*3


# --------------------------------------------------------------------------
# 13b generation accounting: raw output vs post-generation-policy pool
# --------------------------------------------------------------------------
def test_ledger_separates_raw_generation_from_the_generation_policy_output():
    routes, planar = self_identical_layout()
    dedup = run(routes, planar, mode='R', spec=StrategySpec('DEDUP', exact_dedup=True), budget=4000)
    plain = run(routes, planar, mode='R', spec=StrategySpec('PLAIN'), budget=4000)
    for result in (dedup, plain):
        ledger = result['ledger']
        assert ledger['generated_candidates'] == ledger['generated_candidates_raw']
        assert ledger['generated_candidates_after_generation_policy'] <= \
            ledger['generated_candidates_raw']
    assert plain['ledger']['generated_candidates_after_generation_policy'] == \
        plain['ledger']['generated_candidates_raw']
    assert dedup['ledger']['generated_candidates_after_generation_policy'] < \
        dedup['ledger']['generated_candidates_raw']
    assert dedup['ledger']['generated_candidates_raw'] - \
        dedup['ledger']['generated_candidates_after_generation_policy'] == \
        dedup['ledger']['dedup_removed_identical_to_current'] + \
        dedup['ledger']['dedup_removed_duplicates']
    # The same distinction exists per step, and the per-step pools add up to the
    # run ledger (these two runs build no RETURN candidate, so a step pool is
    # exactly the post-dedup candidate list of both victims).
    step = dedup['steps'][0]
    assert step['raw_generated_candidates'] == 36
    assert step['generated_candidates'] == 35
    assert step['raw_generated_candidates'] > step['generated_candidates']
    assert sum(s['generated_candidates'] for s in dedup['steps']) == \
        dedup['ledger']['generated_candidates_after_generation_policy']
    assert sum(s['raw_generated_candidates'] for s in dedup['steps']) == \
        dedup['ledger']['generated_candidates_raw']


# --------------------------------------------------------------------------
# 13c generation accounting note contract
# --------------------------------------------------------------------------
def test_generated_candidates_note_is_the_documented_string():
    """The accounting fix declares generated_candidates_note as a STRING that
    states the raw vs post-policy distinction; three comma-separated literals
    make it a tuple of three strings instead."""
    result = run(*crossed_pair_layout(), mode='N', spec=StrategySpec('NOTE'))
    note = result['ledger']['generated_candidates_note']
    assert isinstance(note, str), (
        'generated_candidates_note must be the documented single string, got %r - join the '
        'three literals at src/overnight_engine_3d.py lines 897-899 (drop the commas or use '
        '"".join(...))' % (note,))
    assert 'RAW' in note and 'generated_candidates_after_generation_policy' in note

