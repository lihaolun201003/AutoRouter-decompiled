"""Step 17 (three-dimensional routing v4): continued full-layout optimisation
from a saved 3D terminal state, with one explicit movement-permission switch.

What is reused unchanged from the verified step-15/16 engine:
- candidate generation  : three_layer_assignment_3d.candidate_families
                          (always rebuilt from the FROZEN PLANAR z=0 route, so a
                          relocation replaces the whole rise/elevated/fall
                          structure and can never stack a second one);
- basic acceptance      : layer_assignment_3d.evaluate_elevation;
- full neighbour check  : strategy_v2_3d.full_acceptance (every current route,
                          unresolved != CLEAR, strict global pair decrease,
                          endpoint/XY-projection/C0-C1/transition-radius);
- deterministic target priority, victim order and net-reduction ranking:
                          strategy_v2_3d.target_priority / route_degrees /
                          strategy_rank;
- structural zero-candidate generation cache (keyed on the complete
  generation-input fingerprint) and the dynamic global-layout-version failure
  cache: strategy_v2_3d.generation_cache_hit / generation_input_key /
  failure_cache_hit.

What this module adds is exactly two things:
1. the start state may already be elevated (a saved 3D terminal state is the
   starting point; the frozen planar routes stay the reconstruction basis);
2. `mode`:
   - 'N' only a not-yet-elevated route may move (first elevation);
   - 'R' additionally an already-elevated route may be re-placed (relocation).
   Both modes share target ordering, generation, ranking, caches and
   acceptance; only the set of movable victims differs.

Accounting is deliberately split so that candidates, candidates that passed
full acceptance and actions actually executed are never mixed:
    generated_candidates            - candidates produced by the generator
    candidate_evaluations           - basic evaluations charged to the budget
    full_neighbor_checks            - candidates that reached the full check
    full_acceptance_passes          - candidates that passed the full check
    executed_moves                  - edits actually applied to the layout
A step may produce several full-acceptance passes and still execute one move.
Skipped targets (no movable route, or a cached structural zero-candidate
generation) never consume a candidate evaluation; they are recorded as separate
skip events.

The budget is APPENDED to whatever produced the start state: the historical 720
evaluations that built the common start state are not part of it.
"""
from collections import Counter
from copy import deepcopy
from math import fsum, isfinite
from time import perf_counter

from .geometry_3d import CosineTransition3D
from .clearance_3d import analyze_route3d_clearance
from .layer_assignment_3d import evaluate_elevation
from .three_layer_assignment_3d import candidate_families
from .sequential_elevation_3d import RouteView, pair_status
from .strategy_v2_3d import (failure_cache_hit, full_acceptance, generation_cache_hit,
    generation_input_key, route_degrees, route_layer, strategy_rank, target_points_for,
    target_priority, xy_projection_preserved)

MODES=('N','R')

SKIPPED_ELEVATED_STATUS_N='ROUTE_ALREADY_ELEVATED_NOT_ALLOWED_IN_N'


def allow_relocation_for(mode):
    """The single behavioural difference between the two modes."""
    if mode not in MODES:raise ValueError('MODE_MUST_BE_N_OR_R')
    return mode=='R'


def pair_state_distribution(pairs,elevated):
    """Route-elevation state of every current centre-line near-distance pair."""
    both_unelevated=single_elevated=both_elevated=0
    for a,b in pairs:
        ea,eb=a in elevated,b in elevated
        if ea and eb:both_elevated+=1
        elif ea or eb:single_elevated+=1
        else:both_unelevated+=1
    return dict(both_routes_unelevated=both_unelevated,single_route_elevated=single_elevated,
        both_routes_elevated=both_elevated,total=len(pairs))


def _movable_victims(target,elevated,allow_relocation):
    """Victims this mode is allowed to move, in the caller's victim order."""
    return [r for r in target if allow_relocation or r not in elevated]


def elevation_structure(route):
    """Exactly zero or one rise/fall pair, and nothing on a third layer.

    A relocated candidate is rebuilt from the frozen planar route, so it
    replaces the previous rise/elevated/fall structure instead of stacking a
    second one. Returns (ok, reason); the layers are the exact configured
    planes, so equality is exact."""
    transitions=[(i,p) for i,p in enumerate(route.primitives) if isinstance(p,CosineTransition3D)]
    if not transitions:
        for p in route.primitives:
            if p.start.z!=0. or p.end.z!=0.:
                return False,'NONZERO_LAYER_WITHOUT_TRANSITION'
        return True,None
    if len(transitions)!=2:return False,'TRANSITION_COUNT_%d'%len(transitions)
    (i,up),(j,down)=transitions
    height=up.end.z
    if up.start.z!=0.:return False,'RISE_NOT_STARTED_ON_LAYER_ZERO'
    if not height>0.:return False,'RISE_TARGET_LAYER_MUST_BE_ELEVATED'
    if down.start.z!=height:return False,'FALL_NOT_STARTED_ON_ELEVATED_LAYER'
    if down.end.z!=0.:return False,'FALL_NOT_ENDED_ON_LAYER_ZERO'
    if j<=i:return False,'FALL_BEFORE_RISE'
    for k,p in enumerate(route.primitives):
        if k in (i,j):continue
        if p.start.z not in (0.,height) or p.end.z not in (0.,height):
            return False,'PRIMITIVE_OUTSIDE_THE_TWO_LAYER_PLANES'
    return True,None


def run_full_layout_v4(initial_routes,planar,config,*,mode,appended_candidate_budget,
                       max_targets=200,window_slack_mm=1e-5,generation_failure_cache=True,
                       saved_crossings=None,initial_pairs=None,initial_uncertain=None,
                       progress=None):
    """Continue one full-layout optimisation run from a saved 3D terminal state.

    Every accepted edit: keeps endpoints, keeps the XY projection of the frozen
    planar route, rebuilds the whole elevation structure from the frozen planar
    route, satisfies C0/C1 and the true transition curvature radius, is checked
    against EVERY current other route, never treats an unresolved pair as CLEAR,
    and strictly reduces the global near-distance pair count.

    `initial_pairs` / `initial_uncertain` may be supplied by the caller (a
    verified full rescan of the start state); otherwise this function performs
    the full scan itself. Inputs are read-only; the baseline is asserted
    unchanged before returning.
    """
    if mode not in MODES:raise ValueError('MODE_MUST_BE_N_OR_R')
    if type(appended_candidate_budget) is not int or appended_candidate_budget<1:
        raise ValueError('APPENDED_CANDIDATE_BUDGET_MUST_BE_POSITIVE_INTEGER')
    if type(max_targets) is not int or max_targets<1:raise ValueError('INVALID_MAX_TARGETS')
    if type(generation_failure_cache) is not bool:
        raise ValueError('GENERATION_FAILURE_CACHE_MUST_BE_BOOLEAN')
    if type(window_slack_mm) not in (int,float) or not isfinite(window_slack_mm) or window_slack_mm<0:
        raise ValueError('WINDOW_SLACK_MUST_BE_FINITE_AND_NONNEGATIVE')
    config.validate()
    if len(initial_routes)!=len(planar):raise ValueError('SCALE_MISMATCH')
    if any(i!=r.route_id for i,r in initial_routes.items()):raise ValueError('ROUTE_ID_MISMATCH')
    if any(i!=r.route_id for i,r in planar.items()):raise ValueError('PLANAR_ROUTE_ID_MISMATCH')
    for i,r in initial_routes.items():
        if any(p.start.z!=p.end.z and not isinstance(p,CosineTransition3D) for p in r.primitives):
            raise ValueError('ONLY_COSINE_TRANSITIONS_MAY_CHANGE_Z')
        ok,reason=xy_projection_preserved(r,planar[i])
        if not ok:raise ValueError(('INITIAL_XY_MISMATCH',i,reason))
        if r.start_point!=planar[i].start_point or r.end_point!=planar[i].end_point:
            raise ValueError(('INITIAL_ENDPOINT_MISMATCH',i))
    allow_relocation=allow_relocation_for(mode)
    started=perf_counter()
    frozen=deepcopy(initial_routes);routes=deepcopy(initial_routes)
    views={i:RouteView.prepare(r) for i,r in routes.items()}
    plan=deepcopy(planar)
    route_version={i:0 for i in routes}          # per-route change counter (anchor memo)
    elevated={i for i,r in routes.items()
        if any(isinstance(p,CosineTransition3D) for p in r.primitives)}
    initial_elevated_route_count=len(elevated)
    initial_total_length=sum(r.total_length() for r in routes.values())
    planar_total_length=sum(r.total_length() for r in plan.values())
    if initial_pairs is None:
        pairs=set();uncertain=set();scan_started=perf_counter()
        for a,b in _sorted_combinations(routes):
            status=pair_status(views[a],views[b],config.clearance_mm)
            if status=='COLLISION':pairs.add((a,b))
            elif status!='CLEAR':uncertain.add((a,b))
        scan_seconds=perf_counter()-scan_started
    else:
        pairs={tuple(p) for p in initial_pairs}
        uncertain={tuple(p) for p in (initial_uncertain or ())}
        scan_seconds=0.0
    for a,b in pairs:
        if a not in routes or b not in routes or a==b:raise ValueError(('INVALID_INITIAL_PAIR',a,b))
    initial_pairs_set=set(pairs);initial_uncertain_set=set(uncertain)
    initial_state_distribution=pair_state_distribution(pairs,elevated)
    if progress:progress(dict(phase='INITIAL_DONE',mode=mode,routes=len(routes),
        collisions=len(pairs),uncertain=len(uncertain),seconds=perf_counter()-started))

    generation_cache_enabled=bool(generation_failure_cache)
    gen_failure_records={};generation_skip_events=[];route_skip_events=[]
    layout_version=0;failure_cache={}
    anchor_memo={}
    steps=[];curve=[dict(step=0,collision_pair_count=len(pairs),candidate_evaluations=0,
        cumulative_removed=0,cumulative_created=0)]
    used=0;generated_total=0;full_checks=0;full_passes=0
    aborted=False;stop_reason=None;aborted_steps=0
    assignment_started=perf_counter()

    def dynamic_anchors(target,moved,other):
        """Current-pair anchors. Saved planar CROSS points win; otherwise the
        current collision analysis of the two CURRENT routes supplies them.
        Memoised on both routes' change counters only, so an anchor change after
        either route moves re-enables the cached structural check."""
        saved_points=(saved_crossings or {}).get(target)
        if saved_points:return list(saved_points)
        key=(target,moved,route_version[moved],route_version[other])
        if key in anchor_memo:return anchor_memo[key]
        report=analyze_route3d_clearance(routes[moved],routes[other],config.clearance_mm)
        if report['status']!='COLLISION':
            anchor_memo[key]=None
            return None
        points=target_points_for(report,None)
        anchor_memo[key]=points
        return points

    def structural_zero_candidates_cached(target,movable):
        """True only when EVERY route this mode may move for `target` has a
        recorded zero-candidate generation under an identical generation-input
        key. A non-zero record is a dynamic outcome and never a hit; a missing
        record, a key mismatch, or a changed anchor re-enables the target."""
        if not movable:return False
        if any((target,m) not in gen_failure_records for m in movable):return False
        for m in movable:
            other=target[1] if m==target[0] else target[0]
            points=dynamic_anchors(target,m,other)
            if points is None:return False
            key=generation_input_key(plan[m],points,config,window_slack_mm=window_slack_mm)
            if not generation_cache_hit(gen_failure_records,target,m,key):return False
        return True

    while len(steps)<max_targets:
        degrees=route_degrees(pairs)
        pending={p for p in pairs if not failure_cache_hit(failure_cache,p,layout_version)}
        target=None
        while pending:
            candidate_target=min(pending,key=lambda p:target_priority(p,degrees))
            movable=_movable_victims(candidate_target,elevated,allow_relocation)
            if not movable:
                route_skip_events.append(dict(target_pair=candidate_target,step_index=len(steps)+1,
                    reason='NO_MOVABLE_ROUTE_IN_MODE',mode=mode,layout_version=layout_version,
                    elevated_victims=sorted(candidate_target)))
                pending.discard(candidate_target);continue
            if generation_cache_enabled and structural_zero_candidates_cached(candidate_target,movable):
                generation_skip_events.append(dict(target_pair=candidate_target,
                    step_index=len(steps)+1,layout_version=layout_version,mode=mode,
                    movable_victims=sorted(movable),
                    cached_generated_counts={str(m):gen_failure_records[(candidate_target,m)]['generated_count']
                        for m in movable}))
                pending.discard(candidate_target);continue
            target=candidate_target;break
        if target is None:
            stop_reason='NO_ELIGIBLE_TARGETS';break
        order=sorted(target,key=lambda r:(degrees.get(r,0),r))
        step=dict(step_index=len(steps)+1,target_pair=target,victim_order=order,mode=mode,
            allow_relocation=allow_relocation,
            victim_degrees={str(r):degrees.get(r,0) for r in order},victim_attempts=[],
            global_collision_pairs_before=len(pairs),elevated_routes_before=sorted(elevated),
            layout_version_before=layout_version,candidate_evaluations_before=used,
            cumulative_removed_before=curve[-1]['cumulative_removed'],
            cumulative_created_before=curve[-1]['cumulative_created'])
        if progress:progress(dict(phase='TARGET_START',mode=mode,step=step['step_index'],
            target=target,degrees=step['victim_degrees'],seconds=perf_counter()-started))
        eligible=[];step_aborted=False
        for victim_index,moved in enumerate(order):
            va=dict(route_id=moved,priority_index=victim_index,candidates=[],
                movement='RELOCATION' if moved in elevated else 'FIRST_ELEVATION')
            step['victim_attempts'].append(va)
            if moved in elevated and not allow_relocation:
                va['status']=SKIPPED_ELEVATED_STATUS_N;continue
            other=target[1] if moved==target[0] else target[0]
            current_report=analyze_route3d_clearance(routes[moved],routes[other],config.clearance_mm)
            if current_report['status']!='COLLISION':
                raise AssertionError('Current near-distance set disagrees with the pair analysis')
            points=target_points_for(current_report,(saved_crossings or {}).get(target))
            try:
                candidates,failure=candidate_families(plan[moved],target,points,config,
                    window_slack_mm=window_slack_mm)
            except ValueError as ex:
                candidates,failure=[],str(ex)
            va.update(generated_count=len(candidates),generation_failure=failure,
                generator_route_source='FROZEN_PLANAR_LAYER_ZERO',
                relocated_from_layer=route_layer(routes[moved]) if moved in elevated else None)
            if generation_cache_enabled:
                gen_failure_records[(target,moved)]=dict(
                    key=generation_input_key(plan[moved],points,config,window_slack_mm=window_slack_mm),
                    generated_count=len(candidates),mode_independent=True,failure=failure)
            generated_total+=len(candidates)
            old_neighbors={b if a==moved else a for a,b in pairs if moved in (a,b)}
            current_length=routes[moved].total_length()
            for candidate_index,candidate in enumerate(candidates):
                if used>=appended_candidate_budget:
                    step_aborted=True;aborted=True;break
                used+=1
                basic=evaluate_elevation(candidate,routes[moved],routes[other],config)
                row=dict(candidate_index=candidate_index,basic_status=basic['status'],
                    basic_reasons=basic['reasons'],rise_window=candidate.rise_window,
                    fall_window=candidate.fall_window,target_layer_id=candidate.layer_to,
                    victim_id=moved,movement=va['movement'],extra_length_mm=candidate.extra_length_mm,
                    elevated_length_mm=candidate.elevated_length_mm)
                va['candidates'].append(row)
                if basic['status']!='ACCEPTED_TARGET_PAIR_ONLY':
                    row['status']='BASIC_REJECTED';row['full_reasons']=None;continue
                full,after_status=full_acceptance(candidate,moved,plan[moved],current_length,
                    views,old_neighbors,config)
                row.update(full)
                full_checks+=1
                if row['status']=='ACCEPTED_FULL':
                    full_passes+=1
                    eligible.append(dict(candidate=candidate,row=row,
                        after_status=after_status,**row))
            if step_aborted:break
        step['full_acceptance_passes']=len(eligible)
        winner=min(eligible,key=strategy_rank) if eligible else None
        if winner is None:
            if step_aborted:
                step['status']='ABORTED_CANDIDATE_BUDGET';step['candidate_budget_hit']=True
                aborted_steps+=1
            else:
                failure_cache[target]=layout_version
                movable_attempts=[va for va in step['victim_attempts']
                    if va.get('status')!=SKIPPED_ELEVATED_STATUS_N]
                if not movable_attempts:step['status']='NO_MOVABLE_ROUTE'
                elif all(va.get('generated_count',0)==0 for va in movable_attempts):
                    step['status']='NO_CANDIDATES_GENERATED'
                elif all(row['status']!='ACCEPTED_FULL' for va in movable_attempts
                        for row in va['candidates']):
                    step['status']='ALL_CANDIDATES_REJECTED'
                else:step['status']='NO_ELIGIBLE_WINNER'
        else:
            c=winner['candidate'];moved=c.route_id
            selected_attempt=next((va for va in step['victim_attempts']
                if va['route_id']==moved and va.get('status')!=SKIPPED_ELEVATED_STATUS_N),None)
            assert selected_attempt is not None and 'status' not in selected_attempt
            selected_attempt['status']='SELECTED'
            previous_length=routes[moved].total_length()
            routes[moved]=deepcopy(c.route);views[moved]=RouteView.prepare(routes[moved])
            structure_ok,structure_reason=elevation_structure(routes[moved])
            assert structure_ok,structure_reason
            route_version[moved]+=1
            layout_version+=1
            if moved in elevated:
                moved_kind='RELOCATION';move_status='RELOCATED'
            else:
                elevated.add(moved);moved_kind='FIRST_ELEVATION';move_status='ELEVATED'
            pairs={p for p in pairs if moved not in p}
            uncertain={p for p in uncertain if moved not in p}
            for neighbor,status in winner['after_status'].items():
                pair=tuple(sorted((moved,neighbor)))
                if status=='COLLISION':pairs.add(pair)
                elif status!='CLEAR':uncertain.add(pair)
            assert step['global_collision_pairs_before']-len(pairs)==winner['row']['net_collision_reduction']>0
            assert target not in pairs
            new_length=routes[moved].total_length()
            step.update(status=move_status,moved_route_id=moved,movement=moved_kind,
                selected_candidate_index=winner['row']['candidate_index'],
                selected_victim_priority_index=selected_attempt['priority_index'],
                victim_collision_degree_before=step['victim_degrees'][str(moved)],
                route_collision_count_before=winner['row']['before_collision_count'],
                route_collision_count_after=winner['row']['after_collision_count'],
                old_collisions_removed=winner['row']['old_collisions_removed'],
                new_collisions_created=winner['row']['new_collisions_created'],
                net_collision_reduction=winner['row']['net_collision_reduction'],
                step_length_delta_mm=new_length-previous_length,
                extra_length_mm_vs_planar=winner['row']['extra_length_mm'],
                transition_count=winner['row']['transition_count'],
                target_layer_id=c.layer_to,rise_window=c.rise_window,fall_window=c.fall_window,
                route_length_before_mm=previous_length,route_length_after_mm=new_length,
                layout_version_after=layout_version,structure_rebuilt_from_planar=True,
                second_victim_success=selected_attempt['priority_index']==1)
            if not step.get('candidate_budget_hit'):step['candidate_budget_hit']=False
        for va in step['victim_attempts']:
            if 'status' in va:continue
            if va.get('generated_count',0)==0:va['status']='NO_CANDIDATES_GENERATED'
            else:va['status']='NO_IMPROVING_CANDIDATE'
        step['global_collision_pairs_after']=len(pairs)
        step['candidate_evaluations_after']=used
        step.setdefault('candidate_budget_hit',False)
        steps.append(step)
        last=curve[-1]
        curve.append(dict(step=step['step_index'],collision_pair_count=len(pairs),
            candidate_evaluations=used,
            cumulative_removed=last['cumulative_removed']+len(step.get('old_collisions_removed',())),
            cumulative_created=last['cumulative_created']+len(step.get('new_collisions_created',())),
            status=step['status'],movement=step.get('movement')))
        if progress:progress(dict(phase='TARGET_DONE',mode=mode,step=step['step_index'],
            status=step['status'],collisions=len(pairs),candidate_evaluations=used,
            seconds=perf_counter()-started))
        if aborted:
            stop_reason='CANDIDATE_BUDGET_EXHAUSTED';break
    if stop_reason is None:stop_reason='TARGET_LIMIT'
    assert initial_routes==frozen
    assert all(routes[i].start_point==plan[i].start_point and routes[i].end_point==plan[i].end_point
        for i in routes)
    moves=[s for s in steps if s['status'] in ('ELEVATED','RELOCATED')]
    first_moves=[s for s in moves if s['movement']=='FIRST_ELEVATION']
    relocation_moves=[s for s in moves if s['movement']=='RELOCATION']
    final_total_length=sum(r.total_length() for r in routes.values())
    stage_length_delta=final_total_length-initial_total_length
    step_delta_total=fsum(s['step_length_delta_mm'] for s in moves)
    assert abs(stage_length_delta-step_delta_total)<1e-6
    final_transition_count=sum(isinstance(p,CosineTransition3D) for r in routes.values()
        for p in r.primitives)
    rows=[row for s in steps for va in s['victim_attempts'] for row in va['candidates']]
    assert len(rows)==used
    basic_rejections=Counter(r for row in rows if row['status']=='BASIC_REJECTED'
        for r in (row.get('basic_reasons') or []))
    full_rejections=Counter(r for row in rows if row['status']=='REJECTED_FULL'
        for r in (row.get('full_reasons') or []))
    generation_failures=Counter(str(va.get('generation_failure'))
        for s in steps for va in s['victim_attempts'] if va.get('generated_count',0)==0)
    checkpoints={}
    for mark in (720,1440,2880):
        reached=[row for row in curve if row['candidate_evaluations']<=mark]
        if reached:
            checkpoints[str(mark)]=dict(candidate_evaluations=reached[-1]['candidate_evaluations'],
                collision_pair_count=reached[-1]['collision_pair_count'],
                cumulative_removed=reached[-1]['cumulative_removed'],
                cumulative_created=reached[-1]['cumulative_created'])
    ledger=dict(mode=mode,allow_relocation=allow_relocation,
        appended_candidate_budget=appended_candidate_budget,
        historical_evaluations_excluded=720,
        historical_budget_note=('the 720 candidate evaluations that produced the common start state '
            'are not part of this budget'),
        max_targets=max_targets,target_attempts=len(steps),
        route_count=len(routes),
        initial_collision_pair_count=len(initial_pairs_set),final_collision_pair_count=len(pairs),
        net_collision_reduction=len(initial_pairs_set)-len(pairs),
        reduction_percent=100*(len(initial_pairs_set)-len(pairs))/len(initial_pairs_set) if initial_pairs_set else 0.,
        initial_unresolved_pair_count=len(initial_uncertain_set),final_unresolved_pair_count=len(uncertain),
        initial_pair_state_distribution=initial_state_distribution,
        final_pair_state_distribution=pair_state_distribution(pairs,elevated),
        total_old_collisions_removed=sum(len(s['old_collisions_removed']) for s in moves),
        total_new_collisions_created=sum(len(s['new_collisions_created']) for s in moves),
        accepted_moves=len(moves),first_elevations=len(first_moves),relocations=len(relocation_moves),
        first_elevation_old_removed=sum(len(s['old_collisions_removed']) for s in first_moves),
        first_elevation_new_created=sum(len(s['new_collisions_created']) for s in first_moves),
        first_elevation_net_reduction=sum(s['net_collision_reduction'] for s in first_moves),
        relocation_old_removed=sum(len(s['old_collisions_removed']) for s in relocation_moves),
        relocation_new_created=sum(len(s['new_collisions_created']) for s in relocation_moves),
        relocation_net_reduction=sum(s['net_collision_reduction'] for s in relocation_moves),
        first_elevation_step_length_delta_mm=fsum(s['step_length_delta_mm'] for s in first_moves),
        relocation_step_length_delta_mm=fsum(s['step_length_delta_mm'] for s in relocation_moves),
        step_length_delta_min_mm=min((s['step_length_delta_mm'] for s in moves),default=0.),
        initial_elevated_route_count=initial_elevated_route_count,
        final_elevated_route_count=len(elevated),
        layer_route_counts={str(k):v for k,v in sorted(Counter(route_layer(r) for r in routes.values()).items())},
        initial_total_length_mm=initial_total_length,final_total_length_mm=final_total_length,
        stage_length_delta_mm=stage_length_delta,
        total_step_length_delta_mm=step_delta_total,
        planar_total_length_mm=planar_total_length,
        start_extra_length_vs_planar_mm=initial_total_length-planar_total_length,
        final_extra_length_vs_planar_mm=final_total_length-planar_total_length,
        final_transition_count=final_transition_count,
        generated_candidates=generated_total,candidate_evaluations=used,
        appended_candidate_budget_used_percent=100*used/appended_candidate_budget,
        full_neighbor_checks=full_checks,full_acceptance_passes=full_passes,
        executed_moves=len(moves),
        budget_exhausted=stop_reason=='CANDIDATE_BUDGET_EXHAUSTED',
        budget_used_up=used>=appended_candidate_budget,
        aborted_steps=aborted_steps,
        aborted_steps_that_still_executed_a_move=sum(1 for s in steps
            if s.get('candidate_budget_hit') and s['status'] in ('ELEVATED','RELOCATED')),
        failed_no_movable_route=sum(s['status']=='NO_MOVABLE_ROUTE' for s in steps),
        failed_no_candidates=sum(s['status']=='NO_CANDIDATES_GENERATED' for s in steps),
        failed_all_rejected=sum(s['status']=='ALL_CANDIDATES_REJECTED' for s in steps),
        failed_no_winner=sum(s['status']=='NO_ELIGIBLE_WINNER' for s in steps),
        zero_candidate_victim_attempts=sum(1 for s in steps for va in s['victim_attempts']
            if va.get('generated_count',0)==0),
        already_elevated_victim_skips=sum(1 for s in steps for va in s['victim_attempts']
            if va.get('status')==SKIPPED_ELEVATED_STATUS_N),
        relocation_victim_attempts=sum(1 for s in steps for va in s['victim_attempts']
            if va.get('movement')=='RELOCATION' and va.get('status')!=SKIPPED_ELEVATED_STATUS_N),
        relocation_candidate_evaluations=sum(len(va['candidates']) for s in steps
            for va in s['victim_attempts'] if va.get('movement')=='RELOCATION'
            and va.get('status')!=SKIPPED_ELEVATED_STATUS_N),
        relocation_victims_selected=sum(1 for s in steps for va in s['victim_attempts']
            if va.get('movement')=='RELOCATION' and va.get('status')=='SELECTED'),
        first_elevation_victim_attempts=sum(1 for s in steps for va in s['victim_attempts']
            if va.get('movement')=='FIRST_ELEVATION'),
        first_elevation_candidate_evaluations=sum(len(va['candidates']) for s in steps
            for va in s['victim_attempts'] if va.get('movement')=='FIRST_ELEVATION'),
        generation_failure_cache_enabled=generation_cache_enabled,
        generation_cache_records=len(gen_failure_records),
        generation_cache_zero_candidate_records=sum(1 for r in gen_failure_records.values()
            if r['generated_count']==0),
        generation_skip_events=len(generation_skip_events),
        generation_skipped_target_count=len({tuple(e['target_pair']) for e in generation_skip_events}),
        no_movable_route_skip_events=len(route_skip_events),
        no_movable_route_skipped_target_count=len({tuple(e['target_pair']) for e in route_skip_events}),
        skipped_events_consumed_no_candidate_evaluation=True,
        basic_rejection_reason_counts=dict(basic_rejections),
        full_rejection_reason_counts=dict(full_rejections),
        generation_failure_reason_counts=dict(generation_failures),
        budget_checkpoints=checkpoints,
        window_slack_mm=float(window_slack_mm),
        stop_reason=stop_reason,
        initial_pair_scan_seconds=scan_seconds,
        assignment_seconds=perf_counter()-assignment_started,
        runtime_seconds=perf_counter()-started,
        baseline_unchanged=True)
    return dict(mode=mode,allow_relocation=allow_relocation,routes=routes,steps=steps,curve=curve,
        ledger=ledger,initial_collision_pairs=sorted(initial_pairs_set),
        final_collision_pairs=sorted(pairs),initial_unresolved_pairs=sorted(initial_uncertain_set),
        final_unresolved_pairs=sorted(uncertain),elevated_route_ids=sorted(elevated),
        relocated_route_ids=sorted(s['moved_route_id'] for s in relocation_moves),
        generation_skips=generation_skip_events,route_skips=route_skip_events)


def _sorted_combinations(routes):
    from itertools import combinations
    return combinations(sorted(routes),2)
