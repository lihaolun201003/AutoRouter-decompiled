"""Overnight unified 3D engine: one verified loop, pluggable scheduling policies.

Generalises the verified step-17 driver (src/strategy_v4_3d.py) so that v5
(target scheduling), v6 (candidate evaluation), v7 (target coverage) and the
eight extra mechanisms (A..H) are each a SINGLE pre-declared factor. Every
switch defaults to the verified v4 behaviour, so a default StrategySpec must
reproduce the v4 group results; tests/test_overnight_engine_3d.py and a real
LEGACY re-run assert that equivalence.

Reused unchanged from the verified engine:
  generation      three_layer_assignment_3d.candidate_families (always rebuilt
                  from the FROZEN PLANAR z=0 route -> a move replaces the whole
                  structure and can never stack a second one)
  basic acceptance layer_assignment_3d.evaluate_elevation
  full check      strategy_v2_3d.full_acceptance (every current route, unresolved
                  != CLEAR, strict global pair decrease, endpoints/XY/C0-C1/radius)
  ranking         strategy_v2_3d.strategy_rank (winner selection only)
  caches          generation_input_key/generation_cache_hit (structural
                  zero-candidate, whole generation fingerprint) and
                  failure_cache_hit (dynamic, invalidated by layout version)

Accounting is never mixed: generated / offered / evaluated / full-checked /
full-passed / executed stay separate, and an UNEVALUATED candidate is never
recorded as a rejection.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from math import fsum, isfinite
from time import perf_counter

from .geometry_3d import (CosineTransition3D, LineSegment3D, PlanarArcSegment3D,
    PathWindowTransition3D, TRANSITION_TYPES)
from .clearance_3d import analyze_route3d_clearance, analyze_route3d_self_clearance, _parameter_xy
from .geometry_3d_diagnostics import analyze_route3d_joins
from .models import Point3D
from .layer_assignment_3d import evaluate_elevation
from .three_layer_assignment_3d import candidate_families, GENERATION_DOMAINS
from .sequential_elevation_3d import RouteView, pair_status
from .strategy_v2_3d import (failure_cache_hit, full_acceptance, generation_cache_hit,
    generation_input_key, route_degrees, route_layer, strategy_rank, target_points_for,
    target_priority, window_rank_key, xy_projection_preserved)

MODES = ('N', 'R')
TARGET_POLICIES = ('LEGACY', 'STRATIFIED')
EVALUATION_POLICIES = ('E0_EXHAUSTIVE', 'E1_ORDERED_EXHAUSTIVE', 'E2_ORDERED_K16')
TRAVERSAL_POLICIES = ('BASE', 'COVERAGE')
SKIPPED_ELEVATED_STATUS_N = 'ROUTE_ALREADY_ELEVATED_NOT_ALLOWED_IN_N'
NOT_EVALUATED = 'NOT_EVALUATED'
NE_K_PREFIX = 'PER_TARGET_K_PREFIX'
NE_BUDGET = 'CANDIDATE_BUDGET_EXHAUSTED'
MOVED_STATUSES = ('ELEVATED', 'RELOCATED', 'RETURNED_TO_PLANE')
# Only these generation-accounting keys are summed over generation calls; every
# other key of the per-call statistics (cap, layer id, planar run, crossing
# offsets, ...) is a setting or a geometry value and must never be accumulated.
ADDITIVE_GENERATION_COUNTERS = ('line_window_candidates', 'path_window_candidates',
                                'path_window_dedup_removed', 'path_window_curvature_rejected',
                                'path_window_build_rejected', 'path_window_cap_truncated',
                                'path_window_pairs_before_rejection', 'anchor_count')


class StrategySpec:
    """Every formal factor of one run, frozen before any formal evaluation.

    Defaults reproduce the verified v4 configuration exactly."""

    __slots__ = ('name', 'target_policy', 'evaluation_policy', 'traversal_policy', 'max_targets',
                 'k_per_target', 'family_round_robin', 'relocation_side_reserve', 'waiting_age',
                 'route_coverage', 'multi_anchor', 'exact_dedup', 'decision_cache',
                 'return_action', 'cache_structural_skips', 'window_slack_mm',
                 'generation_domain', 'path_window_settings', 'stage_length_cap_mm', 'notes')

    def __init__(self, name, *, target_policy='LEGACY', evaluation_policy='E0_EXHAUSTIVE',
                 traversal_policy='BASE', max_targets=200, k_per_target=16,
                 family_round_robin=False, relocation_side_reserve=0, waiting_age=False,
                 route_coverage=False, multi_anchor=False, exact_dedup=False,
                 decision_cache=False, return_action=False, cache_structural_skips=False,
                 window_slack_mm=1e-5, generation_domain='LINE_ONLY', path_window_settings=None,
                 stage_length_cap_mm=None, notes=''):
        self.name = name; self.target_policy = target_policy
        self.evaluation_policy = evaluation_policy; self.traversal_policy = traversal_policy
        self.max_targets = max_targets; self.k_per_target = k_per_target
        self.family_round_robin = family_round_robin
        self.relocation_side_reserve = relocation_side_reserve
        self.waiting_age = waiting_age; self.route_coverage = route_coverage
        self.multi_anchor = multi_anchor; self.exact_dedup = exact_dedup
        self.decision_cache = decision_cache; self.return_action = return_action
        self.cache_structural_skips = cache_structural_skips
        self.window_slack_mm = window_slack_mm
        self.generation_domain = generation_domain
        self.path_window_settings = None if path_window_settings is None \
            else dict(path_window_settings)
        self.stage_length_cap_mm = stage_length_cap_mm
        self.notes = notes
        self.validate()

    def validate(self):
        if not isinstance(self.name, str) or not self.name:
            raise ValueError('STRATEGY_NAME_REQUIRED')
        if self.target_policy not in TARGET_POLICIES:
            raise ValueError('UNSUPPORTED_TARGET_POLICY')
        if self.evaluation_policy not in EVALUATION_POLICIES:
            raise ValueError('UNSUPPORTED_EVALUATION_POLICY')
        if self.traversal_policy not in TRAVERSAL_POLICIES:
            raise ValueError('UNSUPPORTED_TRAVERSAL_POLICY')
        if self.generation_domain not in GENERATION_DOMAINS:
            raise ValueError('UNSUPPORTED_GENERATION_DOMAIN')
        if self.path_window_settings is not None:
            if not isinstance(self.path_window_settings, dict):
                raise ValueError('PATH_WINDOW_SETTINGS_MUST_BE_A_DICT')
            allowed = {'placements', 'length_factors', 'cap'}
            if set(self.path_window_settings) - allowed:
                raise ValueError('UNKNOWN_PATH_WINDOW_SETTING')
            for key in ('placements', 'length_factors'):
                if key in self.path_window_settings:
                    values = tuple(self.path_window_settings[key])
                    if not values or any(type(v) not in (int, float) or not isfinite(v) or v < 0
                                         for v in values):
                        raise ValueError('PATH_WINDOW_' + key.upper() + '_MUST_BE_NONNEGATIVE_NUMBERS')
            if 'cap' in self.path_window_settings:
                if type(self.path_window_settings['cap']) is not int or self.path_window_settings['cap'] < 1:
                    raise ValueError('PATH_WINDOW_CAP_MUST_BE_A_POSITIVE_INTEGER')
        if self.stage_length_cap_mm is not None:
            if type(self.stage_length_cap_mm) not in (int, float) \
                    or not isfinite(self.stage_length_cap_mm) or self.stage_length_cap_mm <= 0:
                raise ValueError('STAGE_LENGTH_CAP_MUST_BE_A_POSITIVE_FINITE_NUMBER')
        if self.generation_domain == 'LINE_ONLY' and self.path_window_settings is not None:
            raise ValueError('PATH_WINDOW_SETTINGS_REQUIRE_THE_PATH_WINDOW_DOMAIN')
        if type(self.max_targets) is not int or self.max_targets < 1:
            raise ValueError('INVALID_MAX_TARGETS')
        if type(self.k_per_target) is not int or self.k_per_target < 1:
            raise ValueError('INVALID_K_PER_TARGET')
        if type(self.relocation_side_reserve) is not int or self.relocation_side_reserve < 0:
            raise ValueError('INVALID_RELOCATION_SIDE_RESERVE')
        if self.relocation_side_reserve and self.evaluation_policy != 'E2_ORDERED_K16':
            raise ValueError('SIDE_RESERVE_REQUIRES_THE_K16_EVALUATION_POLICY')
        if self.relocation_side_reserve > self.k_per_target:
            raise ValueError('SIDE_RESERVE_EXCEEDS_K')
        if self.family_round_robin and self.evaluation_policy != 'E2_ORDERED_K16':
            raise ValueError('FAMILY_ROUND_ROBIN_REQUIRES_THE_K16_EVALUATION_POLICY')
        if self.traversal_policy == 'COVERAGE' and not self.route_coverage:
            raise ValueError('COVERAGE_TRAVERSAL_MUST_DECLARE_ROUTE_COVERAGE')
        if type(self.window_slack_mm) not in (int, float) or not isfinite(self.window_slack_mm) \
                or self.window_slack_mm < 0:
            raise ValueError('WINDOW_SLACK_MUST_BE_FINITE_AND_NONNEGATIVE')
        for flag in ('family_round_robin', 'waiting_age', 'route_coverage', 'multi_anchor',
                     'exact_dedup', 'decision_cache', 'return_action', 'cache_structural_skips'):
            if type(getattr(self, flag)) is not bool:
                raise ValueError('FACTOR_FLAGS_MUST_BE_BOOLEAN:' + flag)

    def as_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}

    def path_window_key(self):
        """Frozen, hashable form of the path-window enumeration settings."""
        if self.path_window_settings is None:
            return None
        settings = self.path_window_settings
        return (tuple(float(v) for v in settings.get('placements', ())),
                tuple(float(v) for v in settings.get('length_factors', ())),
                int(settings.get('cap', 0)))

    def generation_settings(self):
        """Everything that changes WHAT generation/dedup produces; folded into the
        structural zero-candidate cache key so a zero recorded under different
        generation settings can never be reused."""
        return (float(self.window_slack_mm), self.multi_anchor, self.exact_dedup,
                self.return_action, self.generation_domain, self.path_window_key())

    def evaluation_settings(self):
        return (self.evaluation_policy, self.k_per_target, self.family_round_robin,
                self.relocation_side_reserve)


def allow_relocation_for(mode):
    if mode not in MODES:
        raise ValueError('MODE_MUST_BE_N_OR_R')
    return mode == 'R'


def pair_state_distribution(pairs, elevated):
    both_unelevated = single_elevated = both_elevated = 0
    for a, b in pairs:
        ea, eb = a in elevated, b in elevated
        if ea and eb:
            both_elevated += 1
        elif ea or eb:
            single_elevated += 1
        else:
            both_unelevated += 1
    return dict(both_routes_unelevated=both_unelevated, single_route_elevated=single_elevated,
                both_routes_elevated=both_elevated, total=len(pairs))


def elevation_state_class(target, elevated):
    """UU / UE / EE: how many of the two routes are currently elevated.

    A REACHABILITY PROXY for the scheduler, never a claim about which side has a
    legal generation window."""
    return ('UU', 'UE', 'EE')[sum(1 for r in target if r in elevated)]


def elevation_structure(route):
    """Exactly ONE logical rise (0 -> h) and ONE logical fall (h -> 0).

    Judged on the LOGICAL z-profile, never on the number of transition
    primitives: one logical ramp may be split into several CONSECUTIVE
    transition primitives (physical fragments) that are monotone in the same
    direction, and a path window may itself consist of several planar pieces.
    Rejected are a second ramp, a ramp out of order, a non-monotone ramp, a
    plateau on a level other than 0 or the target height, and any primitive
    that changes height without being a transition.
    """
    legs=[]
    for p in route.primitives:
        z0,z1=p.start.z,p.end.z
        if isinstance(p,TRANSITION_TYPES):
            if z1==z0:
                return False,'TRANSITION_WITH_NO_HEIGHT_CHANGE'
            legs.append((z0,z1,'RISE' if z1>z0 else 'FALL'))
        else:
            if z0!=z1:
                return False,'NON_TRANSITION_PRIMITIVE_CHANGES_HEIGHT'
            legs.append((z0,z1,'LEVEL'))
    if not legs:
        return False,'EMPTY_ROUTE'
    if all(kind=='LEVEL' for _,_,kind in legs):
        if all(z==0. for z,_,_ in legs):
            return True,None
        return False,'NONZERO_LAYER_WITHOUT_TRANSITION'
    count=len(legs);index=0
    while index<count and legs[index][2]=='LEVEL':
        if legs[index][0]!=0.:
            return False,'ROUTE_DOES_NOT_START_ON_LAYER_ZERO'
        index+=1
    if index>=count:
        return False,'INCOMPLETE_RISE_OR_FALL'
    height=None
    while index<count and legs[index][2]=='RISE':
        z0,z1,_=legs[index]
        expected=0. if height is None else height
        if z0!=expected:
            return False,'RISE_FRAGMENTS_ARE_NOT_CONTINUOUS'
        if z1<=z0:
            return False,'RISE_NOT_MONOTONE'
        height=z1;index+=1
    if height is None or height<=0.:
        return False,'RISE_TARGET_LAYER_MUST_BE_ELEVATED'
    while index<count and legs[index][2]=='LEVEL':
        if legs[index][0]!=height:
            return False,'PLATEAU_ON_A_THIRD_LEVEL'
        index+=1
    if index<count and legs[index][2]=='RISE':
        levels=sorted({v for z0,z1,_ in legs for v in (z0,z1)})
        positive=[z for z in levels if z>0.]
        return False,'LAYER_COUNT_%d' % (1+len(positive))
    fall_fragments=0
    while index<count and legs[index][2]=='FALL':
        z0,z1,_=legs[index]
        if z0!=height:
            return False,'FALL_FRAGMENTS_ARE_NOT_CONTINUOUS'
        if z1>=z0:
            return False,'FALL_NOT_MONOTONE'
        height=z1;index+=1;fall_fragments+=1
    if fall_fragments==0:
        return False,'INCOMPLETE_RISE_OR_FALL'
    if height!=0.:
        return False,'FALL_DOES_NOT_RETURN_TO_LAYER_ZERO'
    while index<count and legs[index][2]=='LEVEL':
        if legs[index][0]!=0.:
            return False,'PLATEAU_ON_A_THIRD_LEVEL'
        index+=1
    if index!=count:
        return False,'EXTRA_STRUCTURE_AFTER_THE_FALL'
    return True,None


def geometry_fingerprint(route):
    """Complete geometry fingerprint of a 3D route (no ids, no approximation).

    Idea F (exact dedup) and idea G (decision cache keys) both use it. Equal
    fingerprints mean geometrically identical; this is never approximate or
    sampled equality."""
    rows = []
    for p in route.primitives:
        if type(p) is LineSegment3D:
            rows.append(('L', p.start.x, p.start.y, p.start.z, p.end.x, p.end.y, p.end.z))
        elif type(p) is PlanarArcSegment3D:
            rows.append(('A', p.center_x, p.center_y, p.z, p.radius, p.start_angle, p.sweep_angle))
        elif type(p) is CosineTransition3D:
            rows.append(('C', p.start.x, p.start.y, p.start.z, p.end.x, p.end.y, p.end.z))
        elif type(p) is PathWindowTransition3D:
            pieces = tuple(('L', q.start.x, q.start.y, q.start.z, q.end.x, q.end.y, q.end.z)
                           if type(q) is LineSegment3D else
                           ('A', q.center_x, q.center_y, q.z, q.radius, q.start_angle, q.sweep_angle)
                           for q in p.pieces)
            rows.append(('W', pieces, p.z_start, p.z_end))
        else:
            raise TypeError('UNSUPPORTED_PRIMITIVE_IN_FINGERPRINT')
    return tuple(rows)


class _ReturnCandidate:
    """RETURN-to-frozen-plane action for an already elevated route.

    Not an ElevationCandidate3D (it has no transition) but exposes the same
    fields the shared ranking, cost accounting and ledger use."""

    __slots__ = ('route_id', 'target_pair', 'target_crossing', 'layer_from', 'layer_to',
                 'transition_run_mm', 'delta_z', 'required_radius_mm', 'minimum_radius_mm',
                 'rise_window', 'fall_window', 'original_length_mm', 'new_length_mm',
                 'extra_length_mm', 'elevated_length_mm', 'route', 'action', 'is_return')

    def __init__(self, route_id, target_pair, route, original_length_mm, elevated_length_mm):
        self.route_id = route_id
        self.target_pair = tuple(target_pair)
        self.target_crossing = ()
        self.layer_from = 0
        self.layer_to = 0
        self.transition_run_mm = 0.
        self.delta_z = 0.
        self.required_radius_mm = 0.
        self.minimum_radius_mm = float('inf')
        self.rise_window = ()
        self.fall_window = ()
        self.original_length_mm = original_length_mm
        self.new_length_mm = route.total_length()
        self.extra_length_mm = 0.
        self.elevated_length_mm = elevated_length_mm
        self.route = route
        self.action = 'RETURN'
        self.is_return = True

    @property
    def window_kind(self):
        return 'NO_TRANSITION'

    @property
    def rise_span(self):
        return ()

    @property
    def fall_span(self):
        return ()


def evaluate_return_candidate(candidate, original, other, config):
    """Basic acceptance of a RETURN-to-frozen-plane action.

    Mirrors evaluate_elevation for the zero-transition case: the transition
    radius requirement is vacuously satisfied only because there is no
    transition at all, and that fact is recorded explicitly instead of taking
    an unchecked min() over an empty transition set."""
    config.validate()
    r = candidate.route
    r.validate()
    joins = analyze_route3d_joins(r)
    self_result = analyze_route3d_self_clearance(r, config.clearance_mm)
    target = analyze_route3d_clearance(r, other, config.clearance_mm)
    before = analyze_route3d_clearance(original, other, config.clearance_mm)
    endpoints = r.start_point == original.start_point and r.end_point == original.end_point
    transitions = [p for p in r.primitives if isinstance(p, TRANSITION_TYPES)]
    reasons = []
    if transitions:
        reasons.append('RETURN_TARGET_IS_STILL_ELEVATED')
    if not endpoints:
        reasons.append('ENDPOINT_CHANGED')
    if not joins.all_C0 or not joins.all_C1_direction:
        reasons.append('JOIN_FAILED')
    if self_result['status'] != 'CLEAR':
        reasons.append('SELF_COLLISION' if self_result['status'] == 'COLLISION'
                       else 'SELF_' + self_result['status'])
    if before['status'] != 'COLLISION':
        reasons.append('BASELINE_TARGET_NOT_COLLIDING')
    if target['status'] != 'CLEAR':
        reasons.append('TARGET_NOT_CLEARED')
    return dict(status='ACCEPTED_TARGET_PAIR_ONLY' if not reasons else 'REJECTED', reasons=reasons,
                endpoint_invariant=endpoints,
                minimum_radius_mm=float('inf') if not transitions else None,
                zero_transition_radius_check='VACUOUS_NO_TRANSITION' if not transitions else 'N/A',
                self_clearance=self_result, target_before=before, target_after=target,
                target_collision_removed=before['status'] == 'COLLISION' and target['status'] == 'CLEAR',
                local_validation_status='NOT_PERFORMED', new_collisions_created=None,
                old_collisions_removed=None)


def transition_fragment_counts(route):
    """(logical ramps, physical fragments) of one route.

    A logical ramp is a maximal run of CONSECUTIVE transition primitives that
    take z the same way; physical fragments are the sub-curves those primitives
    are made of (a path window split across several planar pieces counts as
    several fragments but still as one logical ramp)."""
    logical = 0; physical = 0; direction = None
    for p in route.primitives:
        if isinstance(p, TRANSITION_TYPES):
            physical += len(p.pieces) if type(p) is PathWindowTransition3D else 1
            current = 'RISE' if p.end.z > p.start.z else 'FALL'
            if current != direction:
                logical += 1; direction = current
        else:
            direction = None
    return logical, physical


def cheap_candidate_score(victim_id, candidate_index, candidate, other_route_id, degrees):
    """Pre-registered cheap ordering estimate for E1/E2.

    Uses ONLY information already available before any acceptance work: the
    current conflict degree of the other route of the target pair and the
    candidate's own declared length cost and geometry indices. It never uses a
    true net reduction, never scans neighbours, and is not an acceptance."""
    kind_rank = 0 if getattr(candidate, 'window_kind', 'LINE_WINDOW_G0') != 'PATH_WINDOW_G1' else 1
    return (-degrees.get(other_route_id, 0), candidate.extra_length_mm,
            candidate.elevated_length_mm, candidate.layer_to, kind_rank,
            window_rank_key(candidate.rise_window), window_rank_key(candidate.fall_window),
            victim_id, candidate_index)


def family_key(candidate):
    """(layer, rise primitive index, fall primitive index) candidate family."""
    rise = candidate.rise_window[0] if candidate.rise_window else -1
    fall = candidate.fall_window[0] if candidate.fall_window else -1
    return (candidate.layer_to, rise, fall)


def order_pool(pool, spec, degrees):
    """Deterministic evaluation order of the merged cross-victim candidate pool."""
    if spec.evaluation_policy == 'E0_EXHAUSTIVE':
        return list(pool)
    for row in pool:
        row['cheap_score'] = cheap_candidate_score(row['victim_id'], row['candidate_index'],
                                                   row['candidate'], row['other'], degrees)
        row['family'] = family_key(row['candidate'])
    if not spec.family_round_robin:
        return sorted(pool, key=lambda r: r['cheap_score'])
    families = defaultdict(list)
    for row in pool:
        families[row['family']].append(row)
    for key in families:
        families[key].sort(key=lambda r: r['cheap_score'])
    # family order = the family whose best candidate is cheapest first; ties by
    # family key. Then each family contributes its next-best candidate in turn.
    family_order = sorted(families, key=lambda k: (families[k][0]['cheap_score'], k))
    ordered = []
    cursor = {k: 0 for k in family_order}
    while len(ordered) < len(pool):
        for key in family_order:
            i = cursor[key]
            if i < len(families[key]):
                ordered.append(families[key][i]); cursor[key] = i + 1
    return ordered


def _select_k_prefix(ordered_pool, spec, order, elevated, per_victim):
    """E2: per-target total K across BOTH sides, never per side.

    With relocation_side_reserve and two movable victims, at least that many
    slots are filled from the elevated victim's own RELOCATION/RETURN candidates
    before the global cheap order fills the remainder, so the elevated side can
    never be crowded out of a shared quota."""
    k = spec.k_per_target
    if spec.relocation_side_reserve and len(order) > 1:
        elevated_victims = [m for m in order if m in elevated
                            and per_victim[m].get('status') != SKIPPED_ELEVATED_STATUS_N]
        chosen = []
        if elevated_victims:
            for row in ordered_pool:
                if len(chosen) >= spec.relocation_side_reserve:
                    break
                if row['victim_id'] in elevated_victims and row['action'] in ('RELOCATION', 'RETURN'):
                    chosen.append(row)
        chosen_ids = {id(r) for r in chosen}
        for row in ordered_pool:
            if len(chosen) >= k:
                break
            if id(row) not in chosen_ids:
                chosen.append(row); chosen_ids.add(id(row))
        return chosen
    return list(ordered_pool[:k])


def run_strategy(initial_routes, planar, config, *, mode, appended_candidate_budget, spec,
                 saved_crossings=None, initial_pairs=None, initial_uncertain=None,
                 generation_failure_cache=True, progress=None):
    if mode not in MODES:
        raise ValueError('MODE_MUST_BE_N_OR_R')
    if type(appended_candidate_budget) is not int or appended_candidate_budget < 1:
        raise ValueError('APPENDED_CANDIDATE_BUDGET_MUST_BE_POSITIVE_INTEGER')
    if type(generation_failure_cache) is not bool:
        raise ValueError('GENERATION_FAILURE_CACHE_MUST_BE_BOOLEAN')
    if not isinstance(spec, StrategySpec):
        raise TypeError('StrategySpec required')
    spec.validate(); config.validate()
    if len(initial_routes) != len(planar):
        raise ValueError('SCALE_MISMATCH')
    if any(i != r.route_id for i, r in initial_routes.items()):
        raise ValueError('ROUTE_ID_MISMATCH')
    for i, r in initial_routes.items():
        if any(p.start.z != p.end.z and not isinstance(p, TRANSITION_TYPES) for p in r.primitives):
            raise ValueError('ONLY_COSINE_TRANSITIONS_MAY_CHANGE_Z')
        ok, reason = xy_projection_preserved(r, planar[i])
        if not ok:
            raise ValueError(('INITIAL_XY_MISMATCH', i, reason))
        if r.start_point != planar[i].start_point or r.end_point != planar[i].end_point:
            raise ValueError(('INITIAL_ENDPOINT_MISMATCH', i))

    allow_relocation = allow_relocation_for(mode)
    started = perf_counter()
    frozen = deepcopy(initial_routes)
    routes = deepcopy(initial_routes)
    views = {i: RouteView.prepare(r) for i, r in routes.items()}
    plan = deepcopy(planar)
    route_version = {i: 0 for i in routes}
    elevated = {i for i, r in routes.items()
                if any(isinstance(p, TRANSITION_TYPES) for p in r.primitives)}
    initial_elevated_route_count = len(elevated)
    initial_total_length = sum(r.total_length() for r in routes.values())
    current_total_length = initial_total_length
    length_cap_checks = 0; length_cap_rejections = 0
    length_cap_rejected_step_mm = 0.; length_cap_rejections_by_action = Counter()
    planar_total_length = sum(r.total_length() for r in plan.values())
    if initial_pairs is None:
        pairs = set(); uncertain = set(); scan_started = perf_counter()
        for a, b in _sorted_combinations(routes):
            status = pair_status(views[a], views[b], config.clearance_mm)
            if status == 'COLLISION':
                pairs.add((a, b))
            elif status != 'CLEAR':
                uncertain.add((a, b))
        scan_seconds = perf_counter() - scan_started
    else:
        pairs = {tuple(p) for p in initial_pairs}
        uncertain = {tuple(p) for p in (initial_uncertain or ())}
        scan_seconds = 0.0
    initial_pairs_set = set(pairs); initial_uncertain_set = set(uncertain)
    initial_state_distribution = pair_state_distribution(pairs, elevated)
    if progress:
        progress(dict(phase='INITIAL_DONE', mode=mode, routes=len(routes), collisions=len(pairs),
                      uncertain=len(uncertain), seconds=perf_counter() - started))

    gen_failure_records = {}; generation_skip_events = []; route_skip_events = []
    generation_accounting = {}
    layout_version = 0; failure_cache = {}; deferral_cache = {}; skip_version = {}
    anchor_memo = {}; decision_cache_store = {}; decision_cache_stats = dict(hits=0, misses=0)
    steps = []
    curve = [dict(step=0, collision_pair_count=len(pairs), candidate_evaluations=0,
                  cumulative_removed=0, cumulative_created=0)]
    used = 0; generated_total = 0; generated_after_policy = 0; full_checks = 0; full_passes = 0
    dedup_removed_total = 0; dedup_removed_identical = 0
    return_candidates_built = 0
    aborted = False; stop_reason = None; aborted_steps = 0
    skipped_rechecks_avoided = 0
    first_seen_step = {}; attempt_counts = Counter(); route_touch_step = {i: -1 for i in routes}
    pair_visit_counts = Counter()
    assignment_started = perf_counter()
    policy = spec

    def dynamic_anchors(target, moved, other):
        saved_points = (saved_crossings or {}).get(target)
        if saved_points:
            return list(saved_points)
        key = (target, moved, route_version[moved], route_version[other])
        if key in anchor_memo:
            return anchor_memo[key]
        report = analyze_route3d_clearance(routes[moved], routes[other], config.clearance_mm)
        if report['status'] != 'COLLISION':
            anchor_memo[key] = None
            return None
        points = target_points_for(report, None)
        anchor_memo[key] = points
        return points

    def witness_anchor(moved, other, base_points, degrees_now):
        """Idea E: one extra legal witness anchor from the victim's current
        conflict neighbourhood, fixed rule = highest current degree then lowest
        route id. The witness is kept only if it lies exactly on the frozen
        planar route, otherwise it is discarded rather than smeared."""
        neighbours = sorted({b if a == moved else a for a, b in pairs if moved in (a, b)} - {other})
        if not neighbours:
            return list(base_points), None
        witness = min(neighbours, key=lambda r: (-degrees_now.get(r, 0), r))
        report = analyze_route3d_clearance(routes[moved], routes[witness], config.clearance_mm)
        if report['status'] != 'COLLISION':
            return list(base_points), None
        kept = []
        for row in report['pair_results']:
            if row['status'] == 'COLLISION' and row.get('closest_point_a') is not None:
                p = row['closest_point_a']
                point = Point3D(p['x'], p['y'], 0.)
                for prim in plan[moved].primitives:
                    t = _parameter_xy(prim, point.x, point.y, 1e-7)
                    if t is not None and prim.point_at(t).distance_to(point) <= 1e-7:
                        kept.append(point); break
        if not kept:
            return list(base_points), None
        merged = list(base_points)
        for point in kept:
            if point not in merged:
                merged.append(point)
        return merged, witness

    def generation_key(moved, points):
        return (generation_input_key(plan[moved], points, config,
                                     window_slack_mm=policy.window_slack_mm),
                policy.generation_settings())

    def structural_zero_candidates_cached(target, movable):
        if not movable:
            return False
        if any((target, m) not in gen_failure_records for m in movable):
            return False
        for m in movable:
            other = target[1] if m == target[0] else target[0]
            points = dynamic_anchors(target, m, other)
            if points is None:
                return False
            if not generation_cache_hit(gen_failure_records, target, m, generation_key(m, points)):
                return False
        return True

    def order_key(p, step_index, degrees_now):
        """The single declared ordering rule of this run.

        waiting_age replaces the primary key by the deterministic target waiting
        age; route_coverage replaces it by the least-recently-touched route of the
        pair. Both keep the original target_priority as the tiebreak, so the
        candidate set and the budget are untouched."""
        if policy.waiting_age:
            age = step_index - first_seen_step.setdefault(p, step_index)
            return (-age,) + target_priority(p, degrees_now)
        if policy.route_coverage:
            return (max(route_touch_step.get(p[0], -1), route_touch_step.get(p[1], -1)),) \
                + target_priority(p, degrees_now)
        return target_priority(p, degrees_now)

    def pick_target(pending, step_index, degrees_now):
        if policy.target_policy == 'STRATIFIED':
            grouped = defaultdict(list)
            for p in pending:
                grouped[elevation_state_class(p, elevated)].append(p)
            ring = ('UU', 'UE', 'EE')
            start = step_index % 3
            for offset in range(3):
                bucket = grouped.get(ring[(start + offset) % 3])
                if bucket:
                    return min(bucket, key=lambda p: order_key(p, step_index, degrees_now))
            return None
        return min(pending, key=lambda p: order_key(p, step_index, degrees_now))

    while len(steps) < policy.max_targets:
        degrees = route_degrees(pairs)
        pending = {p for p in pairs if not failure_cache_hit(failure_cache, p, layout_version)
                   and not failure_cache_hit(deferral_cache, p, layout_version)}
        for p in pending:
            first_seen_step.setdefault(p, len(steps) + 1)
        target = None
        while pending:
            candidate_target = pick_target(pending, len(steps) + 1, degrees)
            if candidate_target is None:
                break
            if policy.cache_structural_skips and failure_cache_hit(skip_version, candidate_target,
                                                                   layout_version):
                skipped_rechecks_avoided += 1
                pending.discard(candidate_target); continue
            movable = [r for r in candidate_target if allow_relocation or r not in elevated]
            if not movable:
                route_skip_events.append(dict(target_pair=candidate_target, step_index=len(steps) + 1,
                                              reason='NO_MOVABLE_ROUTE_IN_MODE', mode=mode,
                                              layout_version=layout_version,
                                              elevated_victims=sorted(candidate_target)))
                if policy.cache_structural_skips:
                    skip_version[candidate_target] = layout_version
                pending.discard(candidate_target); continue
            if generation_failure_cache and structural_zero_candidates_cached(candidate_target, movable):
                generation_skip_events.append(dict(target_pair=candidate_target,
                    step_index=len(steps) + 1, layout_version=layout_version, mode=mode,
                    movable_victims=sorted(movable),
                    cached_generated_counts={str(m): gen_failure_records[(candidate_target, m)]['generated_count']
                                             for m in movable}))
                if policy.cache_structural_skips:
                    skip_version[candidate_target] = layout_version
                pending.discard(candidate_target); continue
            target = candidate_target; break
        if target is None:
            stop_reason = 'NO_ELIGIBLE_TARGETS'; break

        # Additive, behaviour-neutral: where this target sits in the SHARED
        # legacy priority order at the moment it was reached, so the 'first
        # touch rank' question is answered from the run itself.
        own = target_priority(target, degrees)
        target_rank = 1 + sum(1 for p in pairs if target_priority(p, degrees) < own)
        order = sorted(target, key=lambda r: (degrees.get(r, 0), r))
        step = dict(step_index=len(steps) + 1, target_pair=target, victim_order=order, mode=mode,
                    target_priority_rank=target_rank,
                    live_pair_count_at_selection=len(pairs),
                    allow_relocation=allow_relocation, strategy=policy.name,
                    elevation_state_class=elevation_state_class(target, elevated),
                    victim_degrees={str(r): degrees.get(r, 0) for r in order},
                    victim_attempts=[], global_collision_pairs_before=len(pairs),
                    elevated_routes_before=sorted(elevated), layout_version_before=layout_version,
                    candidate_evaluations_before=used,
                    cumulative_removed_before=curve[-1]['cumulative_removed'],
                    cumulative_created_before=curve[-1]['cumulative_created'])
        if progress:
            progress(dict(phase='TARGET_START', mode=mode, step=step['step_index'], target=target,
                          degrees=step['victim_degrees'], seconds=perf_counter() - started))

        # ---- generation for every movable victim, before any evaluation ----
        pool = []; per_victim = {}
        for victim_index, moved in enumerate(order):
            va = dict(route_id=moved, priority_index=victim_index, candidates=[],
                      movement='RELOCATION' if moved in elevated else 'FIRST_ELEVATION')
            step['victim_attempts'].append(va); per_victim[moved] = va
            if moved in elevated and not allow_relocation:
                va['status'] = SKIPPED_ELEVATED_STATUS_N; continue
            other = target[1] if moved == target[0] else target[0]
            current_report = analyze_route3d_clearance(routes[moved], routes[other], config.clearance_mm)
            if current_report['status'] != 'COLLISION':
                raise AssertionError('Current near-distance set disagrees with the pair analysis')
            points = target_points_for(current_report, (saved_crossings or {}).get(target))
            witness = None
            if policy.multi_anchor:
                points, witness = witness_anchor(moved, other, points, degrees)
            generation_stats = {}
            try:
                candidates, failure = candidate_families(
                    plan[moved], target, points, config,
                    window_slack_mm=policy.window_slack_mm,
                    generation_domain=policy.generation_domain,
                    path_window_settings=policy.path_window_settings,
                    stats_out=generation_stats)
            except ValueError as ex:
                candidates, failure = [], str(ex)
                generation_stats = {}
            for key, value in generation_stats.items():
                if key in ADDITIVE_GENERATION_COUNTERS:
                    generation_accounting[key] = generation_accounting.get(key, 0) + value
                elif key == 'path_window_rejection_reasons':
                    row = generation_accounting.setdefault(key, {})
                    for sub_key, sub_value in value.items():
                        row[sub_key] = row.get(sub_key, 0) + sub_value
                elif key == 'no_legal_interval':
                    if any(value.values()):
                        generation_accounting['path_window_empty_legal_intervals'] = (
                            generation_accounting.get('path_window_empty_legal_intervals', 0) + 1)
                elif key == 'length_does_not_fit':
                    generation_accounting['path_window_length_does_not_fit'] = (
                        generation_accounting.get('path_window_length_does_not_fit', 0)
                        + sum(value.values()))
            raw_count = len(candidates)
            dedup_removed = dedup_identical = 0
            if policy.exact_dedup and candidates:
                current_fp = geometry_fingerprint(routes[moved])
                seen = set(); kept = []
                for cand in candidates:
                    fp = geometry_fingerprint(cand.route)
                    if fp == current_fp:
                        dedup_identical += 1; continue
                    if fp in seen:
                        dedup_removed += 1; continue
                    seen.add(fp); kept.append(cand)
                candidates = kept
                dedup_removed_total += dedup_removed
                dedup_removed_identical += dedup_identical
            generated_after_policy += len(candidates)
            # The label is the victim's real movement, so a reservation rule can
            # actually identify an already-elevated victim's candidates. With the
            # uniform historical 'ELEVATE' label the idea-B reservation could never
            # match anything and was a silent no-op (found by the engine test suite).
            row_action = 'RELOCATION' if moved in elevated else 'FIRST_ELEVATION'
            for candidate_index, candidate in enumerate(candidates):
                pool.append(dict(victim_id=moved, candidate_index=candidate_index, candidate=candidate,
                                 other=other, action=row_action,
                                 window_kind=getattr(candidate, 'window_kind', 'LINE_WINDOW_G0')))
            if policy.return_action and moved in elevated:
                current_len = routes[moved].total_length()
                elevated_len = sum(p.length() for p in routes[moved].primitives if p.start.z != 0.
                                   and p.end.z != 0.)
                returned = _ReturnCandidate(moved, target, deepcopy(plan[moved]), current_len, elevated_len)
                return_candidates_built += 1
                # Pre-registered: the RETURN action sits at the HEAD of an elevated
                # victim's pool. Step-17 evidence shows preference-only selection
                # left relocation past rank 21000 and never evaluated it, so the new
                # action must be reachable under a shared budget to be testable.
                pool.insert(sum(v.get('generated_count', 0) for v in step['victim_attempts'][:-1]),
                            dict(victim_id=moved, candidate_index=-1, candidate=returned,
                                 other=other, action='RETURN'))
            generated_total += raw_count
            if generation_failure_cache:
                gen_failure_records[(target, moved)] = dict(
                    key=generation_key(moved, points), generated_count=len(candidates),
                    mode_independent=True, failure=failure, raw_generated_count=raw_count,
                    policy_generation_settings=policy.generation_settings())
            va.update(generated_count=len(candidates), raw_generated_count=raw_count,
                      generation_failure=failure, witness_anchor=witness,
                      dedup_removed_duplicates=dedup_removed,
                      dedup_removed_identical_to_current=dedup_identical,
                      generator_route_source='FROZEN_PLANAR_LAYER_ZERO',
                      relocated_from_layer=route_layer(routes[moved]) if moved in elevated else None,
                      anchor_count=len(points))

        # ---- pre-registered evaluation order / quota over the merged pool ----
        ordered_pool = order_pool(pool, policy, degrees)
        if policy.evaluation_policy == 'E2_ORDERED_K16':
            offered = _select_k_prefix(ordered_pool, policy, order, elevated, per_victim)
        else:
            offered = ordered_pool
        offered_ids = {id(r) for r in offered}
        not_offered = [r for r in pool if id(r) not in offered_ids]
        # generated_candidates is the pool size AFTER the generation policy (dedup);
        # raw_generated_candidates is what the generator produced before it.
        step['raw_generated_candidates'] = sum(va.get('raw_generated_count', 0)
                                               for va in step['victim_attempts'])
        step['generated_candidates'] = len(pool)
        step['offered_candidates'] = len(offered)
        step['k_prefix_truncated_candidates'] = len(not_offered)

        eligible = []; evaluated_count = 0; step_aborted = False
        for row in offered:
            if used >= appended_candidate_budget:
                step_aborted = True; aborted = True; break
            moved = row['victim_id']; candidate = row['candidate']; va = per_victim[moved]
            used += 1; evaluated_count += 1
            if row['action'] == 'RETURN':
                basic = evaluate_return_candidate(candidate, routes[moved], routes[row['other']], config)
            else:
                basic = evaluate_elevation(candidate, routes[moved], routes[row['other']], config)
            entry = dict(candidate_index=row['candidate_index'], basic_status=basic['status'],
                         basic_reasons=basic['reasons'], rise_window=candidate.rise_window,
                         fall_window=candidate.fall_window, target_layer_id=candidate.layer_to,
                         victim_id=moved, movement=va['movement'], action=row['action'],
                         extra_length_mm=candidate.extra_length_mm,
                         elevated_length_mm=candidate.elevated_length_mm,
                         window_kind=row.get('window_kind', 'LINE_WINDOW_G0'),
                         logical_transition_count=transition_fragment_counts(candidate.route)[0],
                         physical_fragment_count=transition_fragment_counts(candidate.route)[1])
            if policy.evaluation_policy != 'E0_EXHAUSTIVE':
                entry['cheap_score'] = [str(x) for x in row.get('cheap_score', ())]
                entry['candidate_family'] = list(row.get('family', ()))
            va['candidates'].append(entry)
            if basic['status'] != 'ACCEPTED_TARGET_PAIR_ONLY':
                entry['status'] = 'BASIC_REJECTED'; entry['full_reasons'] = None; continue
            if policy.stage_length_cap_mm is not None:
                # The basic evaluation above already spent its budget unit: the
                # cost constraint is checked AFTER it and is accounted
                # separately, never hidden as a free filter or a zero candidate.
                step_delta = candidate.route.total_length() - routes[moved].total_length()
                projected_stage = current_total_length + step_delta - initial_total_length
                entry['length_cap_projected_stage_length_mm'] = projected_stage
                length_cap_checks += 1
                if projected_stage > policy.stage_length_cap_mm:
                    entry['status'] = 'REJECTED_STAGE_LENGTH_CAP'
                    entry['full_reasons'] = ['STAGE_LENGTH_CAP_EXCEEDED']
                    entry['length_cap_excess_mm'] = projected_stage - policy.stage_length_cap_mm
                    length_cap_rejections += 1
                    length_cap_rejected_step_mm += step_delta
                    length_cap_rejections_by_action[row['action']] += 1
                    continue
            old_neighbors = {b if a == moved else a for a, b in pairs if moved in (a, b)}
            full, after_status = _full_acceptance(candidate, moved, plan[moved],
                routes[moved].total_length(), views, old_neighbors, config, policy, route_version,
                decision_cache_store, decision_cache_stats)
            entry.update(full)
            full_checks += 1
            if entry['status'] == 'ACCEPTED_FULL':
                full_passes += 1
                eligible.append(dict(candidate=candidate, row=entry, after_status=after_status,
                                     **entry))
        unevaluated = len(pool) - evaluated_count
        for row in offered[evaluated_count:]:
            va = per_victim[row['victim_id']]
            va['candidates'].append(_not_evaluated_row(row, va['movement'], NE_BUDGET))
        for row in not_offered:
            va = per_victim[row['victim_id']]
            va['candidates'].append(_not_evaluated_row(row, va['movement'], NE_K_PREFIX))
        step['evaluated_candidates'] = evaluated_count
        step['not_evaluated_candidates'] = unevaluated
        step['full_acceptance_passes'] = len(eligible)
        step['deferred_target_retriable'] = bool(not_offered)
        step['prefix_evaluated_no_winner_deferred'] = False

        winner = min(eligible, key=strategy_rank) if eligible else None
        if winner is None:
            if step_aborted:
                step['status'] = 'ABORTED_CANDIDATE_BUDGET'; step['candidate_budget_hit'] = True
                aborted_steps += 1
            else:
                movable_attempts = [va for va in step['victim_attempts']
                                    if va.get('status') != SKIPPED_ELEVATED_STATUS_N]
                if unevaluated:
                    # A quota prefix without a winner while candidates remain
                    # unevaluated is a DEFERRED state, never "all rejected", and is
                    # never written into the all-failed cache.
                    step['status'] = 'PREFIX_EVALUATED_NO_WINNER_DEFERRED'
                    step['prefix_evaluated_no_winner_deferred'] = True
                    deferral_cache[target] = layout_version
                else:
                    failure_cache[target] = layout_version
                    if not movable_attempts:
                        step['status'] = 'NO_MOVABLE_ROUTE'
                    elif all(va.get('generated_count', 0) == 0 for va in movable_attempts):
                        step['status'] = 'NO_CANDIDATES_GENERATED'
                    elif all(entry['status'] != 'ACCEPTED_FULL' for va in movable_attempts
                             for entry in va['candidates']):
                        step['status'] = 'ALL_CANDIDATES_REJECTED'
                    else:
                        step['status'] = 'NO_ELIGIBLE_WINNER'
        else:
            c = winner['candidate']; moved = winner['victim_id']
            selected_attempt = per_victim[moved]
            selected_attempt['status'] = 'SELECTED'
            previous_length = routes[moved].total_length()
            routes[moved] = deepcopy(c.route)
            views[moved] = RouteView.prepare(routes[moved])
            structure_ok, structure_reason = elevation_structure(routes[moved])
            assert structure_ok, structure_reason
            route_version[moved] += 1
            layout_version += 1
            if winner['action'] == 'RETURN':
                assert moved in elevated
                moved_kind = 'RETURN'; move_status = 'RETURNED_TO_PLANE'
                elevated.discard(moved)
            elif moved in elevated:
                moved_kind = 'RELOCATION'; move_status = 'RELOCATED'
            else:
                elevated.add(moved); moved_kind = 'FIRST_ELEVATION'; move_status = 'ELEVATED'
            pairs = {p for p in pairs if moved not in p}
            uncertain = {p for p in uncertain if moved not in p}
            for neighbor, status in winner['after_status'].items():
                pair = tuple(sorted((moved, neighbor)))
                if status == 'COLLISION':
                    pairs.add(pair)
                elif status != 'CLEAR':
                    uncertain.add(pair)
            assert step['global_collision_pairs_before'] - len(pairs) == winner['row']['net_collision_reduction'] > 0
            assert target not in pairs
            new_length = routes[moved].total_length()
            current_total_length += new_length - previous_length
            step.update(status=move_status, moved_route_id=moved, movement=moved_kind,
                        action=winner['action'],
                        selected_window_kind=winner['row'].get('window_kind', 'LINE_WINDOW_G0'),
                        selected_candidate_index=winner['row']['candidate_index'],
                        selected_victim_priority_index=selected_attempt['priority_index'],
                        victim_collision_degree_before=step['victim_degrees'][str(moved)],
                        route_collision_count_before=winner['row']['before_collision_count'],
                        route_collision_count_after=winner['row']['after_collision_count'],
                        old_collisions_removed=winner['row']['old_collisions_removed'],
                        new_collisions_created=winner['row']['new_collisions_created'],
                        net_collision_reduction=winner['row']['net_collision_reduction'],
                        step_length_delta_mm=new_length - previous_length,
                        extra_length_mm_vs_planar=winner['row']['extra_length_mm'],
                        transition_count=winner['row']['transition_count'],
                        target_layer_id=c.layer_to, rise_window=c.rise_window, fall_window=c.fall_window,
                        route_length_before_mm=previous_length, route_length_after_mm=new_length,
                        layout_version_after=layout_version, structure_rebuilt_from_planar=True,
                        second_victim_success=selected_attempt['priority_index'] == 1)
            if not step.get('candidate_budget_hit'):
                step['candidate_budget_hit'] = False
        for va in step['victim_attempts']:
            if 'status' in va:
                continue
            if va.get('generated_count', 0) == 0:
                va['status'] = 'NO_CANDIDATES_GENERATED'
            elif va.get('candidates') and all(e['status'] == NOT_EVALUATED for e in va['candidates']):
                va['status'] = 'NOT_REACHED_WITHIN_BUDGET_OR_PREFIX'
            else:
                va['status'] = 'NO_IMPROVING_CANDIDATE'
        for r in target:
            attempt_counts[r] += 1
        pair_visit_counts[target] += 1
        step['unique_target_pair_index'] = pair_visit_counts[target]
        if step['status'] in MOVED_STATUSES:
            for r in target:
                route_touch_step[r] = step['step_index']
        else:
            for va in step['victim_attempts']:
                if any(e['status'] != NOT_EVALUATED for e in va.get('candidates', ())):
                    route_touch_step[va['route_id']] = step['step_index']
        step['global_collision_pairs_after'] = len(pairs)
        step['candidate_evaluations_after'] = used
        step.setdefault('candidate_budget_hit', False)
        steps.append(step)
        last = curve[-1]
        curve.append(dict(step=step['step_index'], collision_pair_count=len(pairs),
                          candidate_evaluations=used,
                          cumulative_removed=last['cumulative_removed'] + len(step.get('old_collisions_removed', ())),
                          cumulative_created=last['cumulative_created'] + len(step.get('new_collisions_created', ())),
                          status=step['status'], movement=step.get('movement')))
        if progress:
            progress(dict(phase='TARGET_DONE', mode=mode, step=step['step_index'],
                          status=step['status'], collisions=len(pairs),
                          candidate_evaluations=used, seconds=perf_counter() - started))
        if aborted:
            stop_reason = 'CANDIDATE_BUDGET_EXHAUSTED'; break
    if stop_reason is None:
        stop_reason = 'TARGET_LIMIT'

    assert initial_routes == frozen
    assert all(routes[i].start_point == plan[i].start_point and routes[i].end_point == plan[i].end_point
               for i in routes)
    moves = [s for s in steps if s['status'] in MOVED_STATUSES]
    first_moves = [s for s in moves if s['movement'] == 'FIRST_ELEVATION']
    relocation_moves = [s for s in moves if s['movement'] == 'RELOCATION']
    return_moves = [s for s in moves if s['movement'] == 'RETURN']
    final_total_length = sum(r.total_length() for r in routes.values())
    stage_length_delta = final_total_length - initial_total_length
    step_delta_total = fsum(s['step_length_delta_mm'] for s in moves)
    assert abs(stage_length_delta - step_delta_total) < 1e-6
    final_transition_count = sum(isinstance(p, TRANSITION_TYPES) for r in routes.values()
                                 for p in r.primitives)
    final_traditional_transition_count = sum(isinstance(p, CosineTransition3D)
                                             for r in routes.values() for p in r.primitives)
    final_path_window_count = sum(type(p) is PathWindowTransition3D for r in routes.values()
                                  for p in r.primitives)
    final_logical_ramps, final_physical_fragments = (
        [sum(v) for v in zip(*[transition_fragment_counts(r) for r in routes.values()])]
        if routes else (0, 0))
    final_pieces_inside_path_windows = sum(
        len(p.pieces) for r in routes.values() for p in r.primitives
        if type(p) is PathWindowTransition3D)
    rows = [entry for s in steps for va in s['victim_attempts'] for entry in va['candidates']]
    assert sum(1 for r in rows if r['status'] != NOT_EVALUATED) == used
    def _row_kind(row):
        return row.get('window_kind') or ('RETURN' if row.get('action') == 'RETURN'
                                          else 'LINE_WINDOW_G0')
    kind_rows = Counter(_row_kind(r) for r in rows)
    basic_rejections = Counter(reason for row in rows if row['status'] == 'BASIC_REJECTED'
                               for reason in (row.get('basic_reasons') or []))
    full_rejections = Counter(reason for row in rows if row['status'] == 'REJECTED_FULL'
                              for reason in (row.get('full_reasons') or []))
    generation_failures = Counter(str(va.get('generation_failure')) for s in steps
                                  for va in s['victim_attempts'] if va.get('generated_count', 0) == 0)
    checkpoints = {}
    for mark in (720, 1440, 2880):
        reached = [row for row in curve if row['candidate_evaluations'] <= mark]
        if reached:
            checkpoints[str(mark)] = dict(candidate_evaluations=reached[-1]['candidate_evaluations'],
                                          collision_pair_count=reached[-1]['collision_pair_count'],
                                          cumulative_removed=reached[-1]['cumulative_removed'],
                                          cumulative_created=reached[-1]['cumulative_created'])
    visited_pairs = [tuple(s['target_pair']) for s in steps]
    visited_sides = [(tuple(s['target_pair']), va['route_id']) for s in steps
                     for va in s['victim_attempts']]
    evaluated_sides = [(tuple(s['target_pair']), va['route_id']) for s in steps
                       for va in s['victim_attempts']
                       if any(e['status'] != NOT_EVALUATED for e in va.get('candidates', ()))]
    cls = ('UU', 'UE', 'EE')
    ledger = dict(
        strategy=policy.name, strategy_spec=policy.as_dict(), mode=mode,
        allow_relocation=allow_relocation, appended_candidate_budget=appended_candidate_budget,
        historical_evaluations_excluded=720,
        historical_budget_note=('the 720 candidate evaluations that produced the common start state '
                                'are not part of this budget'),
        max_targets=policy.max_targets, target_attempts=len(steps), route_count=len(routes),
        initial_collision_pair_count=len(initial_pairs_set), final_collision_pair_count=len(pairs),
        net_collision_reduction=len(initial_pairs_set) - len(pairs),
        reduction_percent=100 * (len(initial_pairs_set) - len(pairs)) / len(initial_pairs_set)
        if initial_pairs_set else 0.,
        initial_unresolved_pair_count=len(initial_uncertain_set),
        final_unresolved_pair_count=len(uncertain),
        initial_pair_state_distribution=initial_state_distribution,
        final_pair_state_distribution=pair_state_distribution(pairs, elevated),
        total_old_collisions_removed=sum(len(s['old_collisions_removed']) for s in moves),
        total_new_collisions_created=sum(len(s['new_collisions_created']) for s in moves),
        accepted_moves=len(moves), first_elevations=len(first_moves),
        relocations=len(relocation_moves), returns=len(return_moves),
        first_elevation_old_removed=sum(len(s['old_collisions_removed']) for s in first_moves),
        first_elevation_new_created=sum(len(s['new_collisions_created']) for s in first_moves),
        first_elevation_net_reduction=sum(s['net_collision_reduction'] for s in first_moves),
        relocation_old_removed=sum(len(s['old_collisions_removed']) for s in relocation_moves),
        relocation_new_created=sum(len(s['new_collisions_created']) for s in relocation_moves),
        relocation_net_reduction=sum(s['net_collision_reduction'] for s in relocation_moves),
        return_old_removed=sum(len(s['old_collisions_removed']) for s in return_moves),
        return_new_created=sum(len(s['new_collisions_created']) for s in return_moves),
        return_net_reduction=sum(s['net_collision_reduction'] for s in return_moves),
        first_elevation_step_length_delta_mm=fsum(s['step_length_delta_mm'] for s in first_moves),
        relocation_step_length_delta_mm=fsum(s['step_length_delta_mm'] for s in relocation_moves),
        return_step_length_delta_mm=fsum(s['step_length_delta_mm'] for s in return_moves),
        step_length_delta_min_mm=min((s['step_length_delta_mm'] for s in moves), default=0.),
        initial_elevated_route_count=initial_elevated_route_count,
        final_elevated_route_count=len(elevated),
        layer_route_counts={str(k): v for k, v in sorted(Counter(route_layer(r)
                                                                 for r in routes.values()).items())},
        initial_total_length_mm=initial_total_length, final_total_length_mm=final_total_length,
        stage_length_delta_mm=stage_length_delta, total_step_length_delta_mm=step_delta_total,
        planar_total_length_mm=planar_total_length,
        start_extra_length_vs_planar_mm=initial_total_length - planar_total_length,
        final_extra_length_vs_planar_mm=final_total_length - planar_total_length,
        final_transition_count=final_transition_count,
        final_traditional_cosine_transition_count=final_traditional_transition_count,
        final_path_window_transition_count=final_path_window_count,
        final_logical_ramp_count=final_logical_ramps,
        final_physical_fragment_count=final_physical_fragments,
        final_physical_pieces_inside_path_windows=final_pieces_inside_path_windows,
        candidates_by_window_kind={k: v for k, v in sorted(kind_rows.items())},
        generated_candidates_by_window_kind={
            k: sum(1 for r in rows if _row_kind(r) == k) for k in sorted(kind_rows)},
        evaluated_candidates_by_window_kind={
            k: sum(1 for r in rows if _row_kind(r) == k and r['status'] != NOT_EVALUATED)
            for k in sorted(kind_rows)},
        full_accepted_candidates_by_window_kind={
            k: sum(1 for r in rows if _row_kind(r) == k and r['status'] == 'ACCEPTED_FULL')
            for k in sorted(kind_rows)},
        executed_moves_by_window_kind=dict(Counter(
            (s.get('selected_window_kind') or 'LINE_WINDOW_G0') for s in moves)),
        first_elevation_moves_by_window_kind=dict(Counter(
            (s.get('selected_window_kind') or 'LINE_WINDOW_G0') for s in first_moves)),
        relocation_moves_by_window_kind=dict(Counter(
            (s.get('selected_window_kind') or 'LINE_WINDOW_G0') for s in relocation_moves)),
        path_window_first_elevation_net_reduction=sum(
            s['net_collision_reduction'] for s in first_moves
            if s.get('selected_window_kind') == 'PATH_WINDOW_G1'),
        path_window_relocation_net_reduction=sum(
            s['net_collision_reduction'] for s in relocation_moves
            if s.get('selected_window_kind') == 'PATH_WINDOW_G1'),
        path_window_step_length_delta_mm=fsum(
            s['step_length_delta_mm'] for s in moves
            if s.get('selected_window_kind') == 'PATH_WINDOW_G1'),
        line_window_step_length_delta_mm=fsum(
            s['step_length_delta_mm'] for s in moves
            if s.get('selected_window_kind') != 'PATH_WINDOW_G1'),
        generation_accounting=generation_accounting,
        stage_length_cap_mm=policy.stage_length_cap_mm,
        stage_length_cap_checks=length_cap_checks,
        stage_length_cap_rejections=length_cap_rejections,
        stage_length_cap_rejected_step_length_mm=length_cap_rejected_step_mm,
        stage_length_cap_rejections_by_action=dict(length_cap_rejections_by_action),
        stage_length_cap_headroom_mm=(None if policy.stage_length_cap_mm is None
                                      else policy.stage_length_cap_mm - stage_length_delta),
        stage_length_cap_used_percent=(None if policy.stage_length_cap_mm is None
                                       else 100 * stage_length_delta / policy.stage_length_cap_mm),
        generated_candidates=generated_total,
        generated_candidates_note=('generated_candidates is the RAW generator output; '
                                   'generated_candidates_after_generation_policy is what survives '
                                   'dedup and any other generation-policy filtering'),
        generated_candidates_raw=generated_total,
        generated_candidates_after_generation_policy=generated_after_policy,
        candidate_evaluations=used,
        appended_candidate_budget_used_percent=100 * used / appended_candidate_budget,
        full_neighbor_checks=full_checks, full_acceptance_passes=full_passes,
        executed_moves=len(moves),
        evaluations_per_action=(used / len(moves)) if moves else None,
        net_reduction_per_evaluation=((len(initial_pairs_set) - len(pairs)) / used) if used else None,
        not_evaluated_candidates=sum(s['not_evaluated_candidates'] for s in steps),
        not_evaluated_by_k_prefix=sum(1 for r in rows if r.get('not_evaluated_reason') == NE_K_PREFIX),
        not_evaluated_by_budget=sum(1 for r in rows if r.get('not_evaluated_reason') == NE_BUDGET),
        budget_exhausted=stop_reason == 'CANDIDATE_BUDGET_EXHAUSTED',
        budget_used_up=used >= appended_candidate_budget, aborted_steps=aborted_steps,
        aborted_steps_that_still_executed_a_move=sum(1 for s in steps if s.get('candidate_budget_hit')
                                                     and s['status'] in MOVED_STATUSES),
        failed_no_movable_route=sum(s['status'] == 'NO_MOVABLE_ROUTE' for s in steps),
        failed_no_candidates=sum(s['status'] == 'NO_CANDIDATES_GENERATED' for s in steps),
        failed_all_rejected=sum(s['status'] == 'ALL_CANDIDATES_REJECTED' for s in steps),
        failed_no_winner=sum(s['status'] == 'NO_ELIGIBLE_WINNER' for s in steps),
        deferred_prefix_no_winner=sum(s['status'] == 'PREFIX_EVALUATED_NO_WINNER_DEFERRED'
                                      for s in steps),
        deferred_target_entries=len(deferral_cache),
        zero_candidate_victim_attempts=sum(1 for s in steps for va in s['victim_attempts']
                                           if va.get('generated_count', 0) == 0),
        already_elevated_victim_skips=sum(1 for s in steps for va in s['victim_attempts']
                                          if va.get('status') == SKIPPED_ELEVATED_STATUS_N),
        relocation_victim_attempts=sum(1 for s in steps for va in s['victim_attempts']
                                       if va.get('movement') == 'RELOCATION'
                                       and va.get('status') != SKIPPED_ELEVATED_STATUS_N),
        relocation_candidates_generated=sum(va.get('generated_count', 0) for s in steps
                                            for va in s['victim_attempts']
                                            if va.get('movement') == 'RELOCATION'),
        relocation_candidate_evaluations=sum(1 for s in steps for va in s['victim_attempts']
                                             if va.get('movement') == 'RELOCATION'
                                             for e in va.get('candidates', ())
                                             if e['status'] != NOT_EVALUATED),
        relocation_victims_selected=sum(1 for s in steps for va in s['victim_attempts']
                                        if va.get('movement') == 'RELOCATION'
                                        and va.get('status') == 'SELECTED'),
        relocation_steps_reaching_evaluation=sum(1 for s in steps if any(
            va.get('movement') == 'RELOCATION'
            and any(e['status'] != NOT_EVALUATED for e in va.get('candidates', ()))
            for va in s['victim_attempts'])),
        first_elevation_victim_attempts=sum(1 for s in steps for va in s['victim_attempts']
                                            if va.get('movement') == 'FIRST_ELEVATION'),
        first_elevation_candidate_evaluations=sum(1 for s in steps for va in s['victim_attempts']
                                                  if va.get('movement') == 'FIRST_ELEVATION'
                                                  for e in va.get('candidates', ())
                                                  if e['status'] != NOT_EVALUATED),
        return_candidates_built=return_candidates_built,
        return_candidate_evaluations=sum(1 for s in steps for va in s['victim_attempts']
                                         for e in va.get('candidates', ())
                                         if e.get('action') == 'RETURN'
                                         and e['status'] != NOT_EVALUATED),
        dedup_removed_duplicates=dedup_removed_total,
        dedup_removed_identical_to_current=dedup_removed_identical,
        decision_cache_hits=decision_cache_stats['hits'],
        decision_cache_misses=decision_cache_stats['misses'],
        decision_cache_enabled=policy.decision_cache,
        pair_status_calls_substituted_by_cache=decision_cache_stats['hits'],
        generation_failure_cache_enabled=generation_failure_cache,
        generation_cache_records=len(gen_failure_records),
        generation_cache_zero_candidate_records=sum(1 for r in gen_failure_records.values()
                                                    if r['generated_count'] == 0),
        generation_skip_events=len(generation_skip_events),
        generation_skipped_target_count=len({tuple(e['target_pair']) for e in generation_skip_events}),
        no_movable_route_skip_events=len(route_skip_events),
        no_movable_route_skipped_target_count=len({tuple(e['target_pair']) for e in route_skip_events}),
        skipped_events_consumed_no_candidate_evaluation=True,
        structural_skip_version_cache_enabled=policy.cache_structural_skips,
        structural_skip_rechecks_avoided=skipped_rechecks_avoided,
        basic_rejection_reason_counts=dict(basic_rejections),
        full_rejection_reason_counts=dict(full_rejections),
        generation_failure_reason_counts=dict(generation_failures),
        budget_checkpoints=checkpoints, window_slack_mm=float(policy.window_slack_mm),
        stop_reason=stop_reason,
        coverage=dict(unique_target_pairs=len(set(visited_pairs)), target_attempts=len(steps),
                      repeated_target_attempts=len(visited_pairs) - len(set(visited_pairs)),
                      unique_target_sides=len(set(visited_sides)),
                      unique_evaluated_target_sides=len(set(evaluated_sides)),
                      unique_routes_attempted=len({r for _, r in visited_sides}),
                      unique_routes_evaluated=len({r for _, r in evaluated_sides}),
                      unique_routes_touched_by_a_move=len({s['moved_route_id'] for s in moves}),
                      max_attempts_on_one_route=max(attempt_counts.values()) if attempt_counts else 0,
                      target_pair_visit_histogram=dict(sorted(Counter(pair_visit_counts.values()).items())),
                      elevation_state_class_attempts={c: sum(1 for s in steps
                                                             if s['elevation_state_class'] == c)
                                                      for c in cls},
                      elevation_state_class_moves={c: sum(1 for s in moves
                                                          if s['elevation_state_class'] == c)
                                                   for c in cls},
                      elevation_state_class_evaluations={c: sum(1 for s in steps
                                                                if s['elevation_state_class'] == c
                                                                for va in s['victim_attempts']
                                                                for e in va.get('candidates', ())
                                                                if e['status'] != NOT_EVALUATED)
                                                         for c in cls},
                      elevation_state_class_first_evaluation_step={c: next(
                          (s['step_index'] for s in steps if s['elevation_state_class'] == c and any(
                              e['status'] != NOT_EVALUATED for va in s['victim_attempts']
                              for e in va.get('candidates', ()))), None) for c in cls},
                      elevation_state_class_deferred={c: sum(
                          1 for s in steps if s['status'] == 'PREFIX_EVALUATED_NO_WINNER_DEFERRED'
                          and s['elevation_state_class'] == c) for c in cls},
                      elevation_state_class_target_pairs={c: len({tuple(s['target_pair']) for s in steps
                                                                  if s['elevation_state_class'] == c})
                                                          for c in cls}),
        initial_pair_scan_seconds=scan_seconds,
        assignment_seconds=perf_counter() - assignment_started,
        runtime_seconds=perf_counter() - started, baseline_unchanged=True)
    return dict(strategy=policy.name, mode=mode, allow_relocation=allow_relocation, routes=routes,
                steps=steps, curve=curve, ledger=ledger,
                initial_collision_pairs=sorted(initial_pairs_set),
                final_collision_pairs=sorted(pairs),
                initial_unresolved_pairs=sorted(initial_uncertain_set),
                final_unresolved_pairs=sorted(uncertain), elevated_route_ids=sorted(elevated),
                relocated_route_ids=sorted(s['moved_route_id'] for s in relocation_moves),
                returned_route_ids=sorted(s['moved_route_id'] for s in return_moves),
                generation_skips=generation_skip_events, route_skips=route_skip_events)


def _not_evaluated_row(row, movement, reason):
    return dict(candidate_index=row['candidate_index'], victim_id=row['victim_id'],
                movement=movement, action=row['action'], status=NOT_EVALUATED, basic_status=None,
                basic_reasons=None, rise_window=row['candidate'].rise_window,
                fall_window=row['candidate'].fall_window, target_layer_id=row['candidate'].layer_to,
                extra_length_mm=row['candidate'].extra_length_mm,
                elevated_length_mm=row['candidate'].elevated_length_mm,
                not_evaluated_reason=reason)


def _full_acceptance(candidate, moved, planar_route, current_length, views, old_neighbors, config,
                     policy, route_version, cache_store, cache_stats):
    """strategy_v2_3d.full_acceptance, optionally with the idea-G decision cache.

    Without the cache this calls the verified function unchanged, so a default
    StrategySpec keeps the historical code path. With the cache, a hit is only
    possible for an identical geometric question: the key contains the complete
    candidate geometry fingerprint, the neighbour id, the neighbour's route
    change counter and the clearance setting."""
    if not policy.decision_cache:
        return full_acceptance(candidate, moved, planar_route, current_length, views,
                               old_neighbors, config)
    candidate_view = RouteView.prepare(candidate.route)
    fingerprint = geometry_fingerprint(candidate.route)
    after_neighbors = set(); unknown = []; after_status = {}
    for neighbor in sorted(views):
        if neighbor == moved:
            continue
        key = (fingerprint, neighbor, route_version[neighbor], config.clearance_mm)
        cached = cache_store.get(key)
        if cached is None:
            status = pair_status(candidate_view, views[neighbor], config.clearance_mm)
            cache_store[key] = status; cache_stats['misses'] += 1
        else:
            status = cached; cache_stats['hits'] += 1
        after_status[neighbor] = status
        if status == 'COLLISION':
            after_neighbors.add(neighbor)
        elif status != 'CLEAR':
            unknown.append(neighbor)
    removed = sorted(old_neighbors - after_neighbors); created = sorted(after_neighbors - old_neighbors)
    xy_ok, xy_reason = xy_projection_preserved(candidate.route, planar_route)
    endpoint_invariant = (candidate.route.start_point == planar_route.start_point and
                          candidate.route.end_point == planar_route.end_point)
    route_id_invariant = candidate.route_id == moved == planar_route.route_id
    transition_count = sum(isinstance(p, TRANSITION_TYPES) for p in candidate.route.primitives)
    step_length_delta = candidate.route.total_length() - current_length
    reasons = []
    if not route_id_invariant:
        reasons.append('ROUTE_ID_CHANGED')
    if not endpoint_invariant:
        reasons.append('ENDPOINT_CHANGED')
    if not xy_ok:
        reasons.append(xy_reason)
    if unknown:
        reasons.append('UNRESOLVED_NEIGHBOR')
    if not (len(removed) - len(created) > 0):
        reasons.append('NO_STRICT_GLOBAL_DECREASE')
    row = dict(before_collision_count=len(old_neighbors), after_collision_count=len(after_neighbors),
               old_collisions_removed=removed, new_collisions_created=created,
               net_collision_reduction=len(removed) - len(created), unresolved_neighbor_ids=unknown,
               checked_neighbor_count=len(after_status), xy_projection_preserved=xy_ok,
               xy_failure_reason=xy_reason, endpoint_invariant=endpoint_invariant,
               route_id_invariant=route_id_invariant, transition_count=transition_count,
               step_length_delta_mm=step_length_delta, extra_length_mm=candidate.extra_length_mm,
               full_reasons=reasons, status='ACCEPTED_FULL' if not reasons else 'REJECTED_FULL')
    return row, after_status


def _sorted_combinations(routes):
    from itertools import combinations
    return combinations(sorted(routes), 2)
