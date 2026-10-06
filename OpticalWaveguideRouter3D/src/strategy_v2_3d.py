"""Step 15 experimental module: selection strategies A/B/C on the fixed 0/1/2 mm
three-layer elevation pipeline. New module; all legacy entry points unchanged.

A = the 9-E/9-F decision rules re-implemented inside the shared budget and
    ledger engine (canonical min target, degree victim order, first improving
    victim wins, at most one elevation per route).
B = filter targets this strategy can no longer move (both routes already
    elevated), deterministic conflict-concentrated target priority, both
    victims evaluated, cross-route ranking by net pair reduction. One
    elevation per route is still enforced.
C = B plus relocation of already-elevated routes (new layer and new rise/fall
    windows). Replacement candidates are rebuilt from the frozen planar z=0
    route; the current route only enters evaluation as the comparison
    baseline. Dynamic acceptance failures are cached per target under the
    GLOBAL layout version: any accepted edit anywhere invalidates the entry, so
    a third-party layout change re-enables the target.

Candidate evaluation budget: one unit per evaluate_elevation (basic) call,
rejections included, identical for A/B/C. Frozen from the historical runs:
512 routes -> 720, 1024 routes -> 8172.

Two default-off switches (historical behaviour unchanged):
- generation_failure_cache: an independent structural cache. A target is
  skipped, without consuming the formal target-attempt bound, only when every
  movable victim has a recorded zero-candidate generation under an identical
  generation_input_key (frozen planar geometry, actual anchors, layer planes,
  all settings, window slack). Dynamic acceptance failures keep the
  global-layout-version failure cache and are never skipped by this path.
- window_slack_mm: a strictly positive placement margin for candidate
  windows, passed into generation so a candidate is not placed exactly on the
  clearance threshold (see elevation_candidates). The 0.1 mm clearance
  criterion and the conservative rejection rules are unchanged.
"""
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from itertools import combinations
from math import fsum,hypot,inf,isfinite,pi
from time import perf_counter
from .models import Point3D
from .geometry_3d import (LineSegment3D,PlanarArcSegment3D,CosineTransition3D,
    PathWindowTransition3D,Route3D,TRANSITION_TYPES)
from .clearance_3d import analyze_route3d_clearance,_parameter_xy
from .layer_assignment_3d import evaluate_elevation
from .three_layer_assignment_3d import candidate_families,layer_candidate_rank
from .sequential_elevation_3d import RouteView,pair_status


@dataclass(frozen=True)
class BudgetConfig:
    scale: int
    max_targets: int
    candidate_budget: int
    budget_counts_basic_rejections: bool
    source: str

    def validate(self):
        if type(self.scale) is not int or self.scale<=0:raise ValueError('INVALID_SCALE')
        if type(self.max_targets) is not int or self.max_targets<1:raise ValueError('INVALID_MAX_TARGETS')
        if type(self.candidate_budget) is not int or self.candidate_budget<1:raise ValueError('INVALID_CANDIDATE_BUDGET')
        if self.budget_counts_basic_rejections is not True:
            raise ValueError('BUDGET_MUST_COUNT_BASIC_REJECTIONS')


# Frozen before any B/C run from the saved historical candidate rows:
# 512  three-layer 50 attempts -> 720 evaluate_elevation calls (348 accepted).
# 1024 three-layer 1024 attempts -> 8172 evaluate_elevation calls (4604 accepted).
FROZEN_BUDGETS={
    512:BudgetConfig(512,50,720,True,
        'step_9_f_three_layer_attempts.json: 720 candidate rows over 50 target attempts'),
    1024:BudgetConfig(1024,1024,8172,True,
        'step_10_fixed_1024_attempts.json: 8172 candidate rows over 1024 target attempts'),
}


def frozen_budget(scale):
    if scale not in FROZEN_BUDGETS:raise ValueError('NO_FROZEN_BUDGET_FOR_SCALE')
    config=FROZEN_BUDGETS[scale];config.validate()
    return config


SKIPPED_ELEVATED_STATUSES=frozenset(('ROUTE_ALREADY_ELEVATED','ROUTE_ALREADY_ELEVATED_NOT_ALLOWED_IN_D'))


def failure_cache_hit(failure_cache,pair,layout_version):
    """Global-layout-version cache: a failure recorded under an earlier layout is
    always retried, because full acceptance depends on every neighbour, not only
    on the two routes of the target. Any accepted edit anywhere bumps the
    version, so third-party layout changes invalidate the entry."""
    return failure_cache.get(pair)==layout_version


def generation_input_key(plan_route,points,config,*,window_slack_mm=0.0):
    """Complete fingerprint of every input to candidate generation for one
    (target, victim) task: the frozen planar geometry actually handed to the
    generator, the actual anchor points, every configured layer plane and all
    generation settings including the window slack. Any change yields a
    different key, so a cached structural result is reused only when the
    generation inputs are identical. Never keyed on route ids alone."""
    def _row(p):
        if type(p) is LineSegment3D:
            return ('LINE',p.start.x,p.start.y,p.start.z,p.end.x,p.end.y,p.end.z)
        if type(p) is PlanarArcSegment3D:
            return ('ARC',p.center_x,p.center_y,p.z,p.radius,p.start_angle,p.sweep_angle)
        if type(p) is PathWindowTransition3D:
            pieces=tuple(('LINE',q.start.x,q.start.y,q.start.z,q.end.x,q.end.y,q.end.z)
                         if type(q) is LineSegment3D else
                         ('ARC',q.center_x,q.center_y,q.z,q.radius,q.start_angle,q.sweep_angle)
                         for q in p.pieces)
            return ('PATHWINDOW',pieces,p.z_start,p.z_end)
        return ('COSINE',p.start.x,p.start.y,p.start.z,p.end.x,p.end.y,p.end.z)
    geometry=tuple(_row(p) for p in plan_route.primitives)
    anchors=tuple((p.x,p.y,p.z) for p in points)
    layers=tuple((layer.id,layer.z) for layer in config.layers)
    settings=(config.clearance_mm,config.required_radius_mm,config.transition_policy,
        config.parameter_status,float(window_slack_mm))
    return (geometry,anchors,layers,settings)


def generation_cache_hit(gen_cache,pair,moved,current_key):
    """Structural zero-candidate cache: a hit requires a recorded zero-candidate
    generation under exactly the same generation-input key. A record with a
    non-zero candidate count is a dynamic outcome and never counts as a cached
    structural failure, and a key mismatch re-enables the task."""
    stored=gen_cache.get((pair,moved))
    return stored is not None and stored['generated_count']==0 and stored['key']==current_key


def route_layer(route):
    """Final main layer of a single-elevation route: transition target z or 0."""
    for p in route.primitives:
        if isinstance(p,CosineTransition3D):return int(round(p.end.z))
        if type(p) is PathWindowTransition3D:return int(round(p.end.z))
    return 0


def _primitive_xy_length(p):
    if isinstance(p,PlanarArcSegment3D):return p.radius*abs(p.sweep_angle)
    if type(p) is PathWindowTransition3D:return p.planar_run_mm
    return hypot(p.end.x-p.start.x,p.end.y-p.start.y)


def xy_polyline_length(route):
    return fsum(_primitive_xy_length(p) for p in route.primitives)


def _xy_samples(route):
    """Ordered (cumulative XY length, x, y) samples; arcs subdivided."""
    rows=[];acc=0.
    for p in route.primitives:
        length=_primitive_xy_length(p)
        if type(p) is PathWindowTransition3D:
            # Sample the exact planar sub-curves it covers, each at its own density.
            for k,piece in enumerate(p.pieces):
                if isinstance(piece,PlanarArcSegment3D):
                    n=max(2,min(17,int(abs(piece.sweep_angle)/(pi/32))+1))
                else:
                    n=3
                base=acc+p.piece_offsets[k]
                for j in range(n+1):
                    t=j/n;q=piece.point_at(t)
                    rows.append((base+t*piece.length(),q.x,q.y))
            acc+=length
            continue
        if isinstance(p,PlanarArcSegment3D):n=max(2,min(17,int(abs(p.sweep_angle)/(pi/32))+1))
        else:n=3
        for k in range(n+1):
            t=k/n;q=p.point_at(t)
            rows.append((acc+t*length,q.x,q.y))
        acc+=length
    return rows,acc


def _xy_nearest(route,x,y):
    """Nearest XY projection on the route; returns (distance, XY arc length)."""
    best_distance,best_s=inf,0.
    acc=0.
    for p in route.primitives:
        length=_primitive_xy_length(p)
        if type(p) is PathWindowTransition3D:
            # The window parameter is a planar arc-length fraction, so the
            # cumulative offset is exact without a local re-parameterisation.
            t=_parameter_xy(p,x,y,1e-9)
            points=[(p,t)] if t is not None else [(p,0.),(p,1.)]
            for primitive,tq in points:
                q=primitive.point_at(tq)
                d=hypot(q.x-x,q.y-y)
                if d<best_distance:best_distance,best_s=d,acc+tq*length
            acc+=length
            continue
        t=_parameter_xy(p,x,y,1e-9)
        points=[(p.point_at(t),t)] if t is not None else [(p.point_at(0.),0.),(p.point_at(1.),1.)]
        for q,tq in points:
            d=hypot(q.x-x,q.y-y)
            if d<best_distance:best_distance,best_s=d,acc+tq*length
        acc+=length
    return best_distance,best_s


def xy_projection_preserved(candidate_route,planar_route,*,tol=1e-7):
    """Bidirectional sampled check: same total XY length and every sample of one
    route within tol (position and XY arc length) of the other. Read-only."""
    if candidate_route.route_id!=planar_route.route_id:return False,'ROUTE_ID_CHANGED'
    candidate_samples,candidate_length=_xy_samples(candidate_route)
    planar_samples,planar_length=_xy_samples(planar_route)
    if abs(candidate_length-planar_length)>tol:return False,'XY_TOTAL_LENGTH_CHANGED'
    for s,x,y in candidate_samples:
        distance,planar_s=_xy_nearest(planar_route,x,y)
        if distance>tol:return False,'XY_SAMPLE_OFF_PLANAR'
        if abs(s-planar_s)>tol*max(1.,s):return False,'XY_ARC_LENGTH_MISMATCH'
    for s,x,y in planar_samples:
        distance,candidate_s=_xy_nearest(candidate_route,x,y)
        if distance>tol:return False,'XY_REVERSE_OFF_CANDIDATE'
        if abs(s-candidate_s)>tol*max(1.,s):return False,'XY_REVERSE_ARC_LENGTH_MISMATCH'
    return True,None


def target_points_for(current_report,saved_points):
    """Finite-window anchors. Saved planar CROSS points win; otherwise the
    current pair analysis supplies COLLISION closest points, projected to z=0
    so anchors always lie on the frozen planar route (identical to the legacy
    behaviour whenever the moved route is still on layer 0)."""
    if saved_points:return deepcopy(saved_points)
    values=[]
    for r in current_report['pair_results']:
        if r['status']=='COLLISION' and r.get('closest_point_a') is not None:
            p=r['closest_point_a'];q=Point3D(p['x'],p['y'],0.)
            if q not in values:values.append(q)
    return values


def route_degrees(pairs):
    """Conflict degree per route for the current pair set (single pass)."""
    degrees=Counter()
    for a,b in pairs:degrees[a]+=1;degrees[b]+=1
    return degrees


def target_priority(pair,degrees):
    """Deterministic: conflict-concentrated pairs first (degree sum, degree max).
    `degrees` must be the precomputed Counter from route_degrees."""
    da,db=degrees.get(pair[0],0),degrees.get(pair[1],0)
    return (-(da+db),-max(da,db),pair)


def window_rank_key(window):
    """Canonical, type-compatible form of one elevation window.

    (start primitive, start parameter, end primitive, end parameter) for both
    the historical single-primitive line windows and the v8 path windows that
    may span several primitives; an empty window stays empty. Old and new
    windows therefore sort and group together without a type error."""
    if not window:
        return ()
    if len(window)==4:
        return tuple(window)
    i,u,v=window
    return (i,u,i,v)


def strategy_rank(row):
    """Cross-route rank. Never compares raw after counts across routes: the
    primary key is the net reduction of this move, then creation count,
    length cost of this step, transition count and stable geometry fields."""
    c=row['candidate']
    return (-row['net_collision_reduction'],len(row['new_collisions_created']),
            row['step_length_delta_mm'],row['transition_count'],c.elevated_length_mm,
            c.layer_to,window_rank_key(c.rise_window),window_rank_key(c.fall_window),
            row['victim_id'])


def full_acceptance(candidate,moved,planar_route,current_length,views,old_neighbors,config):
    """Complete check of one basically-accepted candidate against every current
    route. Read-only: nothing outside the returned values is touched."""
    candidate_view=RouteView.prepare(candidate.route)
    after_neighbors=set();unknown=[];after_status={}
    for neighbor in sorted(views):
        if neighbor==moved:continue
        status=pair_status(candidate_view,views[neighbor],config.clearance_mm)
        after_status[neighbor]=status
        if status=='COLLISION':after_neighbors.add(neighbor)
        elif status!='CLEAR':unknown.append(neighbor)
    removed=sorted(old_neighbors-after_neighbors);created=sorted(after_neighbors-old_neighbors)
    xy_ok,xy_reason=xy_projection_preserved(candidate.route,planar_route)
    endpoint_invariant=(candidate.route.start_point==planar_route.start_point and
                        candidate.route.end_point==planar_route.end_point)
    route_id_invariant=candidate.route_id==moved==planar_route.route_id
    transition_count=sum(isinstance(p,TRANSITION_TYPES) for p in candidate.route.primitives)
    step_length_delta=candidate.route.total_length()-current_length
    reasons=[]
    if not route_id_invariant:reasons.append('ROUTE_ID_CHANGED')
    if not endpoint_invariant:reasons.append('ENDPOINT_CHANGED')
    if not xy_ok:reasons.append(xy_reason)
    if unknown:reasons.append('UNRESOLVED_NEIGHBOR')
    if not (len(removed)-len(created)>0):reasons.append('NO_STRICT_GLOBAL_DECREASE')
    row=dict(before_collision_count=len(old_neighbors),after_collision_count=len(after_neighbors),
        old_collisions_removed=removed,new_collisions_created=created,
        net_collision_reduction=len(removed)-len(created),unresolved_neighbor_ids=unknown,
        checked_neighbor_count=len(after_status),xy_projection_preserved=xy_ok,
        xy_failure_reason=xy_reason,endpoint_invariant=endpoint_invariant,
        route_id_invariant=route_id_invariant,transition_count=transition_count,
        step_length_delta_mm=step_length_delta,extra_length_mm=candidate.extra_length_mm,
        full_reasons=reasons,status='ACCEPTED_FULL' if not reasons else 'REJECTED_FULL')
    return row,after_status


def run_fixed_target_diagnostic(initial_routes,planar,config,*,targets,mode,scale,progress=None,
                                saved_crossings=None,budget=None,window_slack_mm=0.0):
    """Fixed, pre-declared target list from a frozen 3D start state.

    One attempt per target, in the given order. mode='D' allows first elevations
    only (B rules on a fixed list); mode='E' also allows relocation of already
    elevated routes. Both modes share the same start, list, order, geometry,
    acceptance rules and candidate-budget ceiling. Read-only on the inputs.

    window_slack_mm is passed straight into candidate generation for both modes
    (see elevation_candidates); it moves window placements by slack/length and
    never relaxes the 0.1 mm clearance criterion or any acceptance rule. The
    structural generation-failure cache is not part of this diagnostic, so the
    only change against the historical D/E diagnostic is this slack. Default
    0.0 reproduces the historical behaviour exactly."""
    if mode not in ('D','E'):raise ValueError('MODE_MUST_BE_D_OR_E')
    if type(window_slack_mm) not in (int,float) or not isfinite(window_slack_mm) or window_slack_mm<0:
        raise ValueError('WINDOW_SLACK_MUST_BE_FINITE_AND_NONNEGATIVE')
    config.validate()
    budget=frozen_budget(scale) if budget is None else budget
    budget.validate()
    if scale!=len(initial_routes) or scale!=len(planar):raise ValueError('SCALE_MISMATCH')
    for i,r in initial_routes.items():
        if any(p.start.z!=p.end.z and not isinstance(p,CosineTransition3D) for p in r.primitives):
            raise ValueError('ONLY_COSINE_TRANSITIONS_MAY_CHANGE_Z')
        ok,reason=xy_projection_preserved(r,planar[i])
        if not ok:raise ValueError(('INITIAL_XY_MISMATCH',i,reason))
    for pair in targets:
        if pair[0]>=pair[1] or pair[0] not in initial_routes or pair[1] not in initial_routes:
            raise ValueError(('INVALID_TARGET',pair))
    started=perf_counter()
    frozen=deepcopy(initial_routes);routes=deepcopy(initial_routes)
    views={i:RouteView.prepare(r) for i,r in routes.items()}
    plan=deepcopy(planar)
    elevated={i for i,r in routes.items()
        if any(isinstance(p,CosineTransition3D) for p in r.primitives)}
    initial_elevated_route_count=len(elevated)
    initial_total_length=sum(r.total_length() for r in routes.values())
    planar_total_length=sum(r.total_length() for r in plan.values())
    pairs=set();uncertain=set();scan_started=perf_counter()
    for a,b in combinations(sorted(routes),2):
        status=pair_status(views[a],views[b],config.clearance_mm)
        if status=='COLLISION':pairs.add((a,b))
        elif status!='CLEAR':uncertain.add((a,b))
    initial_pairs=set(pairs);initial_uncertain=set(uncertain)
    scan_seconds=perf_counter()-scan_started
    if progress:progress(dict(phase='INITIAL_DONE',mode=mode,checked=scale*(scale-1)//2,
        collisions=len(pairs),uncertain=len(uncertain),seconds=perf_counter()-started))
    steps=[];curve=[dict(step=0,collision_pair_count=len(pairs),candidate_evaluations=0)]
    used=0;generated_total=0;full_checks=0;aborted=False;stop_reason=None
    assignment_started=perf_counter()
    for index,target in enumerate(targets):
        if used>=budget.candidate_budget:
            stop_reason='CANDIDATE_BUDGET_EXHAUSTED';break
        degrees=route_degrees(pairs)
        order=sorted(target,key=lambda r:(degrees.get(r,0),r))
        step=dict(step_index=len(steps)+1,target_pair=target,target_index=index,victim_order=order,
            victim_degrees={str(r):degrees.get(r,0) for r in order},victim_attempts=[],
            global_collision_pairs_before=len(pairs),elevated_routes_before=sorted(elevated),
            candidate_evaluations_before=used,mode=mode)
        if progress:progress(dict(phase='TARGET_START',mode=mode,step=step['step_index'],target=target,
            seconds=perf_counter()-started))
        if target not in pairs:
            step['status']='TARGET_NO_LONGER_COLLIDING'
            steps.append(step);continue
        eligible=[];step_aborted=False
        for victim_index,moved in enumerate(order):
            va=dict(route_id=moved,priority_index=victim_index,
                movement='RELOCATION' if moved in elevated else 'FIRST_ELEVATION',candidates=[])
            step['victim_attempts'].append(va)
            if mode=='D' and moved in elevated:
                va['status']='ROUTE_ALREADY_ELEVATED_NOT_ALLOWED_IN_D';continue
            other=target[1] if moved==target[0] else target[0]
            current_report=analyze_route3d_clearance(routes[moved],routes[other],config.clearance_mm)
            if current_report['status']!='COLLISION':
                raise AssertionError('Current collision set disagrees with 9-C target analysis')
            points=target_points_for(current_report,(saved_crossings or {}).get(target))
            try:
                candidates,failure=candidate_families(plan[moved],target,points,config,
                    window_slack_mm=window_slack_mm)
            except ValueError as ex:
                candidates,failure=[],str(ex)
            va.update(generated_count=len(candidates),generation_failure=failure,
                generator_route_source='FROZEN_PLANAR_LAYER_ZERO')
            generated_total+=len(candidates)
            old_neighbors={b if a==moved else a for a,b in pairs if moved in (a,b)}
            current_length=routes[moved].total_length()
            for candidate_index,candidate in enumerate(candidates):
                if used>=budget.candidate_budget:
                    step_aborted=True;aborted=True;break
                used+=1
                basic=evaluate_elevation(candidate,routes[moved],routes[other],config)
                row=dict(candidate_index=candidate_index,basic_status=basic['status'],
                    basic_reasons=basic['reasons'],rise_window=candidate.rise_window,
                    fall_window=candidate.fall_window,target_layer_id=candidate.layer_to,
                    victim_id=moved,extra_length_mm=candidate.extra_length_mm,
                    elevated_length_mm=candidate.elevated_length_mm)
                va['candidates'].append(row)
                if basic['status']!='ACCEPTED_TARGET_PAIR_ONLY':
                    row['status']='BASIC_REJECTED';row['full_reasons']=None;continue
                full,after_status=full_acceptance(candidate,moved,plan[moved],current_length,
                    views,old_neighbors,config)
                row.update(full);full_checks+=1
                if row['status']=='ACCEPTED_FULL':
                    eligible.append(dict(candidate=candidate,row=row,movement=va['movement'],
                        after_status=after_status,**row))
            if step_aborted:break
        if step_aborted:
            step['status']='ABORTED_CANDIDATE_BUDGET'
            steps.append(step)
            stop_reason='CANDIDATE_BUDGET_EXHAUSTED'
            if progress:progress(dict(phase='TARGET_DONE',mode=mode,step=step['step_index'],
                status=step['status'],collisions=len(pairs),candidate_evaluations=used,
                seconds=perf_counter()-started))
            break
        winner=min(eligible,key=strategy_rank) if eligible else None
        if winner is None:
            movable=[va for va in step['victim_attempts']
                if va.get('status')!='ROUTE_ALREADY_ELEVATED_NOT_ALLOWED_IN_D']
            if not movable:
                step['status']='NO_MOVABLE_ROUTE'
            elif all(va.get('generated_count',0)==0 for va in movable):
                step['status']='NO_CANDIDATES_GENERATED'
            elif all(row['status']!='ACCEPTED_FULL' for va in movable for row in va['candidates']):
                step['status']='ALL_CANDIDATES_REJECTED'
            else:
                step['status']='NO_ELIGIBLE_WINNER'
        else:
            c=winner['candidate'];moved=c.route_id
            for va in step['victim_attempts']:
                if va['route_id']==moved and 'status' not in va:va['status']='SELECTED'
            previous_length=routes[moved].total_length()
            routes[moved]=deepcopy(c.route);views[moved]=RouteView.prepare(routes[moved])
            if moved in elevated:pass
            else:elevated.add(moved)
            pairs={p for p in pairs if moved not in p};uncertain={p for p in uncertain if moved not in p}
            for neighbor,status in winner['after_status'].items():
                pair=tuple(sorted((moved,neighbor)))
                if status=='COLLISION':pairs.add(pair)
                elif status!='CLEAR':uncertain.add(pair)
            assert step['global_collision_pairs_before']-len(pairs)==winner['row']['net_collision_reduction']>0
            assert target not in pairs
            step.update(status='RELOCATED' if winner['movement']=='RELOCATION' else 'ELEVATED',
                moved_route_id=moved,movement=winner['movement'],
                selected_candidate_index=winner['row']['candidate_index'],
                selected_victim_priority_index=next(va['priority_index'] for va in step['victim_attempts']
                    if va.get('status')=='SELECTED'),
                route_collision_count_before=winner['row']['before_collision_count'],
                route_collision_count_after=winner['row']['after_collision_count'],
                old_collisions_removed=winner['row']['old_collisions_removed'],
                new_collisions_created=winner['row']['new_collisions_created'],
                net_collision_reduction=winner['row']['net_collision_reduction'],
                step_length_delta_mm=routes[moved].total_length()-previous_length,
                extra_length_mm_vs_planar=winner['row']['extra_length_mm'],
                transition_count=winner['row']['transition_count'],target_layer_id=c.layer_to,
                rise_window=c.rise_window,fall_window=c.fall_window,
                route_length_before_mm=previous_length,route_length_after_mm=routes[moved].total_length())
        step['global_collision_pairs_after']=len(pairs)
        step['candidate_evaluations_after']=used
        steps.append(step)
        curve.append(dict(step=step['step_index'],collision_pair_count=len(pairs),candidate_evaluations=used))
        if progress:progress(dict(phase='TARGET_DONE',mode=mode,step=step['step_index'],
            status=step['status'],collisions=len(pairs),candidate_evaluations=used,
            seconds=perf_counter()-started))
    if stop_reason is None:stop_reason='TARGET_LIST_FINISHED'
    assert initial_routes==frozen
    moves=[s for s in steps if s['status'] in ('ELEVATED','RELOCATED')]
    final_total_length=sum(r.total_length() for r in routes.values())
    final_transition_count=sum(isinstance(p,CosineTransition3D) for r in routes.values() for p in r.primitives)
    ledger=dict(mode=mode,target_count=len(targets),target_attempts=len([s for s in steps
            if s['status']!='TARGET_NO_LONGER_COLLIDING']),
        targets_no_longer_colliding=sum(1 for s in steps if s['status']=='TARGET_NO_LONGER_COLLIDING'),
        initial_collision_pair_count=len(initial_pairs),final_collision_pair_count=len(pairs),
        net_collision_reduction=len(initial_pairs)-len(pairs),
        initial_unresolved_pair_count=len(initial_uncertain),final_unresolved_pair_count=len(uncertain),
        accepted_moves=len(moves),first_elevations=sum(s['status']=='ELEVATED' for s in moves),
        relocations=sum(s['status']=='RELOCATED' for s in moves),
        failed_no_movable_route=sum(s['status']=='NO_MOVABLE_ROUTE' for s in steps),
        failed_no_candidates=sum(s['status']=='NO_CANDIDATES_GENERATED' for s in steps),
        failed_all_rejected=sum(s['status']=='ALL_CANDIDATES_REJECTED' for s in steps),
        failed_no_winner=sum(s['status']=='NO_ELIGIBLE_WINNER' for s in steps),
        aborted_steps=sum(s['status']=='ABORTED_CANDIDATE_BUDGET' for s in steps),
        relocation_victim_attempts=sum(1 for s in steps for va in s['victim_attempts']
            if va.get('movement')=='RELOCATION'
            and va.get('status') not in SKIPPED_ELEVATED_STATUSES),
        relocation_candidate_evaluations=sum(len(va['candidates']) for s in steps
            for va in s['victim_attempts'] if va.get('movement')=='RELOCATION'
            and va.get('status') not in SKIPPED_ELEVATED_STATUSES),
        relocation_victims_selected=sum(1 for s in steps for va in s['victim_attempts']
            if va.get('movement')=='RELOCATION' and va.get('status')=='SELECTED'),
        initial_elevated_route_count=initial_elevated_route_count,
        initial_total_length_mm=initial_total_length,final_total_length_mm=final_total_length,
        step_length_delta_total_mm=final_total_length-initial_total_length,
        planar_total_length_mm=planar_total_length,
        final_extra_length_vs_planar_mm=final_total_length-planar_total_length,
        final_transition_count=final_transition_count,
        generated_candidates=generated_total,full_neighbor_checks=full_checks,
        candidate_evaluations=used,candidate_budget=budget.candidate_budget,
        budget_exhausted=stop_reason=='CANDIDATE_BUDGET_EXHAUSTED',
        stop_reason=stop_reason,initial_pair_scan_seconds=scan_seconds,
        assignment_seconds=perf_counter()-assignment_started,runtime_seconds=perf_counter()-started,
        window_slack_mm=float(window_slack_mm),
        generation_failure_cache_enabled=False,
        baseline_unchanged=True)
    return dict(mode=mode,routes=routes,steps=steps,curve=curve,ledger=ledger,
        initial_collision_pairs=sorted(initial_pairs),final_collision_pairs=sorted(pairs),
        initial_unresolved_pairs=sorted(initial_uncertain),final_unresolved_pairs=sorted(uncertain),
        elevated_route_ids=sorted(elevated))


def run_strategy_v2(initial_routes,planar,config,*,strategy,scale,progress=None,saved_crossings=None,
                    budget=None,allow_elevated_initial=False,generation_failure_cache=False,
                    window_slack_mm=0.0):
    """Shared engine for A/B/C. A reproduces the legacy 9-F step sequence inside
    the same budget and ledger accounting; B and C change decisions only.

    allow_elevated_initial=True accepts an already-elevated 3D state (e.g. the
    saved B terminal state) as the start point; the frozen planar routes stay the
    reconstruction basis for every candidate.

    generation_failure_cache=True (C only) skips a target without consuming the
    formal target-attempt bound when every movable victim has a recorded
    zero-candidate generation under exactly the same generation inputs (frozen
    planar geometry, actual anchors, layer planes, all settings). Dynamic
    failures keep the global-layout-version cache. window_slack_mm is passed
    into candidate generation; both default to the historical behaviour."""
    if strategy not in ('A','B','C'):raise ValueError('STRATEGY_MUST_BE_A_B_OR_C')
    if type(generation_failure_cache) is not bool:raise ValueError('GENERATION_FAILURE_CACHE_MUST_BE_BOOLEAN')
    if type(window_slack_mm) not in (int,float) or not isfinite(window_slack_mm) or window_slack_mm<0:
        raise ValueError('WINDOW_SLACK_MUST_BE_FINITE_AND_NONNEGATIVE')
    config.validate()
    budget=frozen_budget(scale) if budget is None else budget
    budget.validate()
    if type(scale) is not int or scale!=len(initial_routes) or scale!=len(planar):
        raise ValueError('SCALE_MISMATCH')
    if any(i!=r.route_id for i,r in initial_routes.items()):raise ValueError('ROUTE_ID_MISMATCH')
    if any(i!=r.route_id for i,r in planar.items()):raise ValueError('PLANAR_ROUTE_ID_MISMATCH')
    for i,r in initial_routes.items():
        if not allow_elevated_initial and any(
                isinstance(p,CosineTransition3D) or p.start.z!=0 or p.end.z!=0 for p in r.primitives):
            raise ValueError('INITIAL_LAYER_ZERO_REQUIRED')
        if any(p.start.z!=p.end.z and not isinstance(p,CosineTransition3D) for p in r.primitives):
            raise ValueError('ONLY_COSINE_TRANSITIONS_MAY_CHANGE_Z')
        ok,reason=xy_projection_preserved(r,planar[i])
        if not ok:raise ValueError(('INITIAL_XY_MISMATCH',i,reason))
    started=perf_counter()
    frozen=deepcopy(initial_routes);routes=deepcopy(initial_routes)
    views={i:RouteView.prepare(r) for i,r in routes.items()}
    plan=deepcopy(planar)
    initial_total_length=sum(r.total_length() for r in routes.values())
    pairs=set();uncertain=set();initial_checks=0;scan_started=perf_counter()
    for a,b in combinations(sorted(routes),2):
        status=pair_status(views[a],views[b],config.clearance_mm);initial_checks+=1
        if status=='COLLISION':pairs.add((a,b))
        elif status!='CLEAR':uncertain.add((a,b))
        if progress and initial_checks%10000==0:
            progress(dict(phase='INITIAL_COLLISIONS',strategy=strategy,checked=initial_checks,
                collisions=len(pairs),seconds=perf_counter()-started))
    scan_seconds=perf_counter()-scan_started
    initial_pairs=set(pairs);initial_uncertain=set(uncertain)
    if progress:progress(dict(phase='INITIAL_DONE',strategy=strategy,checked=initial_checks,
        collisions=len(pairs),uncertain=len(uncertain),seconds=perf_counter()-started))
    elevated={i for i,r in routes.items()
        if any(isinstance(p,CosineTransition3D) for p in r.primitives)}
    initial_elevated_route_count=len(elevated)
    initial_total_length_mm=initial_total_length
    relocated=set();skipped=set()
    layout_version=0;failure_cache={}
    generation_cache_enabled=bool(generation_failure_cache) and strategy=='C'
    gen_failure_records={};generation_skip_events=[]
    steps=[];curve=[dict(step=0,collision_pair_count=len(pairs),candidate_evaluations=0)]
    used=0;generated_total=0;full_checks=0;aborted=False;stop_reason=None
    assignment_started=perf_counter()

    def structural_zero_candidates_cached(target_pair):
        """A target may be skipped without a formal attempt only when EVERY
        currently movable victim has a zero-candidate generation recorded under
        exactly the same generation inputs. Saved crossing anchors win;
        otherwise the current collision analysis re-derives the dynamic
        anchors, so an anchor change re-enables the target. A non-zero record
        for either victim keeps the target attemptable."""
        if any((target_pair,moved) not in gen_failure_records for moved in target_pair):return False
        for moved in target_pair:
            saved_points=(saved_crossings or {}).get(target_pair)
            if saved_points:
                points=list(saved_points)
            else:
                other=target_pair[1] if moved==target_pair[0] else target_pair[0]
                report=analyze_route3d_clearance(routes[moved],routes[other],config.clearance_mm)
                if report['status']!='COLLISION':return False
                points=target_points_for(report,None)
            key=generation_input_key(plan[moved],points,config,window_slack_mm=window_slack_mm)
            if not generation_cache_hit(gen_failure_records,target_pair,moved,key):return False
        return True

    while len(steps)<budget.max_targets:
        degrees=route_degrees(pairs)
        if strategy=='A':
            pending=pairs-skipped
            target=min(pending) if pending else None
        elif strategy=='B':
            pending={p for p in pairs if not (p[0] in elevated and p[1] in elevated)}-skipped
            target=min(pending,key=lambda p:target_priority(p,degrees)) if pending else None
        else:
            pending={p for p in pairs if not failure_cache_hit(failure_cache,p,layout_version)}
            target=None
            while pending:
                candidate_target=min(pending,key=lambda p:target_priority(p,degrees))
                if not generation_cache_enabled or not structural_zero_candidates_cached(candidate_target):
                    target=candidate_target;break
                generation_skip_events.append(dict(target_pair=candidate_target,
                    step_index=len(steps)+1,layout_version=layout_version,
                    cached_generated_counts={str(m):gen_failure_records[(candidate_target,m)]['generated_count']
                        for m in candidate_target}))
                pending.discard(candidate_target)
        if target is None:
            stop_reason='NO_ELIGIBLE_TARGETS';break
        order=sorted(target,key=lambda r:(degrees.get(r,0),r))
        step=dict(step_index=len(steps)+1,target_pair=target,victim_order=order,
            victim_degrees={str(r):degrees.get(r,0) for r in order},victim_attempts=[],
            global_collision_pairs_before=len(pairs),elevated_routes_before=sorted(elevated),
            layout_version_before=layout_version,candidate_evaluations_before=used)
        if progress:progress(dict(phase='TARGET_START',strategy=strategy,step=step['step_index'],
            target=target,degrees=step['victim_degrees'],seconds=perf_counter()-started))
        eligible=[];step_aborted=False
        for victim_index,moved in enumerate(order):
            va=dict(route_id=moved,priority_index=victim_index,
                movement='RELOCATION' if moved in elevated else 'FIRST_ELEVATION',candidates=[])
            step['victim_attempts'].append(va)
            if strategy in ('A','B') and moved in elevated:
                va['status']='ROUTE_ALREADY_ELEVATED';continue
            other=target[1] if moved==target[0] else target[0]
            current_report=analyze_route3d_clearance(routes[moved],routes[other],config.clearance_mm)
            if current_report['status']!='COLLISION':
                raise AssertionError('Current collision set disagrees with 9-C target analysis')
            points=target_points_for(current_report,(saved_crossings or {}).get(target))
            try:
                candidates,failure=candidate_families(plan[moved],target,points,config,
                    window_slack_mm=window_slack_mm)
            except ValueError as ex:
                candidates,failure=[],str(ex)
            va.update(generated_count=len(candidates),generation_failure=failure,
                generator_route_source='FROZEN_PLANAR_LAYER_ZERO')
            if generation_cache_enabled:
                gen_failure_records[(target,moved)]=dict(
                    key=generation_input_key(plan[moved],points,config,window_slack_mm=window_slack_mm),
                    generated_count=len(candidates),failure=failure)
            generated_total+=len(candidates)
            old_neighbors={b if a==moved else a for a,b in pairs if moved in (a,b)}
            current_length=routes[moved].total_length()
            for index,candidate in enumerate(candidates):
                if used>=budget.candidate_budget:
                    step_aborted=True;aborted=True;break
                used+=1
                basic=evaluate_elevation(candidate,routes[moved],routes[other],config)
                row=dict(candidate_index=index,basic_status=basic['status'],basic_reasons=basic['reasons'],
                    rise_window=candidate.rise_window,fall_window=candidate.fall_window,
                    target_layer_id=candidate.layer_to,victim_id=moved,
                    extra_length_mm=candidate.extra_length_mm,elevated_length_mm=candidate.elevated_length_mm)
                va['candidates'].append(row)
                if basic['status']!='ACCEPTED_TARGET_PAIR_ONLY':
                    row['status']='BASIC_REJECTED';row['full_reasons']=None
                    if progress:progress(dict(phase='CANDIDATE',strategy=strategy,step=step['step_index'],
                        victim=moved,index=index,total=len(candidates),status='BASIC_REJECTED',
                        seconds=perf_counter()-started))
                    continue
                full,after_status=full_acceptance(candidate,moved,plan[moved],current_length,
                    views,old_neighbors,config)
                row.update(full)
                if row['status']=='ACCEPTED_FULL':
                    eligible.append(dict(candidate=candidate,row=row,movement=va['movement'],
                        after_status=after_status,**row))
                full_checks+=1
                if progress:progress(dict(phase='CANDIDATE',strategy=strategy,step=step['step_index'],
                    victim=moved,index=index,total=len(candidates),status=row['status'],
                    after=row['after_collision_count'],seconds=perf_counter()-started))
            if strategy=='A' and eligible:break
            if step_aborted:break
        if strategy=='A':
            winner=min(eligible,key=layer_candidate_rank) if eligible else None
        else:
            winner=min(eligible,key=strategy_rank) if eligible else None
        if winner is None:
            if step_aborted:
                step['status']='ABORTED_CANDIDATE_BUDGET'
            elif strategy=='A':
                skipped.add(target)
                step['status']='BOTH_ALREADY_ELEVATED' if all(i in elevated for i in target) else 'NO_IMPROVING_SINGLE_ELEVATION'
            elif strategy=='B':
                skipped.add(target);step['status']='NO_ACCEPTABLE_MOVE'
            else:
                failure_cache[target]=layout_version
                step['status']='NO_ACCEPTABLE_MOVE'
        else:
            c=winner['candidate'];moved=c.route_id
            selected_attempt=next((va for va in step['victim_attempts']
                if va['route_id']==moved and 'status' not in va),None)
            if selected_attempt is not None:selected_attempt['status']='SELECTED'
            previous_length=routes[moved].total_length()
            routes[moved]=deepcopy(c.route);views[moved]=RouteView.prepare(routes[moved])
            layout_version+=1
            if moved in elevated:relocated.add(moved)
            else:elevated.add(moved)
            pairs={p for p in pairs if moved not in p};uncertain={p for p in uncertain if moved not in p}
            for neighbor,status in winner['after_status'].items():
                pair=tuple(sorted((moved,neighbor)))
                if status=='COLLISION':pairs.add(pair)
                elif status!='CLEAR':uncertain.add(pair)
            assert step['global_collision_pairs_before']-len(pairs)==winner['row']['net_collision_reduction']>0
            assert target not in pairs
            step_length_delta=routes[moved].total_length()-previous_length
            # second_victim_success: the SELECTED victim attempt's order index,
            # not the last attempt of the step.
            assert selected_attempt is not None
            step.update(status='RELOCATED' if winner['movement']=='RELOCATION' else 'ELEVATED',
                moved_route_id=moved,selected_candidate_index=winner['row']['candidate_index'],
                selected_victim_priority_index=selected_attempt['priority_index'],
                victim_collision_degree_before=step['victim_degrees'][str(moved)],
                route_collision_count_before=winner['row']['before_collision_count'],
                route_collision_count_after=winner['row']['after_collision_count'],
                old_collisions_removed=winner['row']['old_collisions_removed'],
                new_collisions_created=winner['row']['new_collisions_created'],
                net_collision_reduction=winner['row']['net_collision_reduction'],
                step_length_delta_mm=step_length_delta,
                extra_length_mm_vs_planar=winner['row']['extra_length_mm'],
                transition_count=winner['row']['transition_count'],target_layer_id=c.layer_to,
                rise_window=c.rise_window,fall_window=c.fall_window,
                route_length_before_mm=previous_length,route_length_after_mm=routes[moved].total_length(),
                second_victim_success=selected_attempt['priority_index']==1,
                layout_version_after=layout_version)
        for va in step['victim_attempts']:
            if 'status' in va:continue
            if va.get('generated_count',0)==0:va['status']='NO_CANDIDATES_GENERATED'
            else:va['status']='NO_IMPROVING_CANDIDATE'
        step['global_collision_pairs_after']=len(pairs)
        step['candidate_evaluations_after']=used
        steps.append(step)
        curve.append(dict(step=step['step_index'],collision_pair_count=len(pairs),candidate_evaluations=used))
        if progress:progress(dict(phase='TARGET_DONE',strategy=strategy,step=step['step_index'],
            status=step['status'],collisions=len(pairs),candidate_evaluations=used,
            seconds=perf_counter()-started,steps=None))
        if aborted:
            stop_reason='CANDIDATE_BUDGET_EXHAUSTED';break
    if stop_reason is None:stop_reason='TARGET_LIMIT'
    assert initial_routes==frozen
    moves=[s for s in steps if s['status'] in ('ELEVATED','RELOCATED')]
    final_total_length=sum(r.total_length() for r in routes.values())
    final_extra_length=final_total_length-initial_total_length
    assert abs(final_extra_length-fsum(s['step_length_delta_mm'] for s in moves))<1e-6
    final_transition_count=sum(isinstance(p,CosineTransition3D) for r in routes.values() for p in r.primitives)
    ledger=dict(
        initial_collision_pair_count=len(initial_pairs),final_collision_pair_count=len(pairs),
        net_collision_reduction=len(initial_pairs)-len(pairs),
        reduction_percent=100*(len(initial_pairs)-len(pairs))/len(initial_pairs) if initial_pairs else 0.,
        total_old_collisions_removed=sum(len(s['old_collisions_removed']) for s in moves),
        total_new_collisions_created=sum(len(s['new_collisions_created']) for s in moves),
        initial_unresolved_pair_count=len(initial_uncertain),final_unresolved_pair_count=len(uncertain),
        accepted_moves=len(moves),first_elevations=sum(s['status']=='ELEVATED' for s in moves),
        relocations=sum(s['status']=='RELOCATED' for s in moves),
        elevated_route_count=len(elevated),relocated_route_count=len(relocated),
        initial_total_length_mm=initial_total_length,final_total_length_mm=final_total_length,
        final_extra_length_mm=final_extra_length,
        total_step_length_delta_mm=fsum(s['step_length_delta_mm'] for s in moves),
        final_transition_count=final_transition_count,
        layer_route_counts={str(k):v for k,v in sorted(Counter(route_layer(r) for r in routes.values()).items())},
        target_attempts=len(steps),skipped_already_clear=0,
        targets_with_any_elevated_route=sum(1 for s in steps
            if any(i in set(s['elevated_routes_before']) for i in s['target_pair'])),
        targets_with_both_elevated_route=sum(1 for s in steps
            if all(i in set(s['elevated_routes_before']) for i in s['target_pair'])),
        relocation_victim_attempts=sum(1 for s in steps for va in s['victim_attempts']
            if va.get('movement')=='RELOCATION'
            and va.get('status') not in SKIPPED_ELEVATED_STATUSES),
        relocation_candidate_evaluations=sum(len(va['candidates']) for s in steps
            for va in s['victim_attempts'] if va.get('movement')=='RELOCATION'
            and va.get('status') not in SKIPPED_ELEVATED_STATUSES),
        relocation_victims_selected=sum(1 for s in steps for va in s['victim_attempts']
            if va.get('movement')=='RELOCATION' and va.get('status')=='SELECTED'),
        initial_elevated_route_count=initial_elevated_route_count,
        first_move_fraction_percent=100*sum(1 for s in moves if s['status']=='ELEVATED')/len(moves) if moves else 0.,
        failed_without_winner=sum(s['status'] in ('NO_IMPROVING_SINGLE_ELEVATION','NO_ACCEPTABLE_MOVE') for s in steps),
        both_already_elevated=sum(s['status']=='BOTH_ALREADY_ELEVATED' for s in steps),
        already_elevated_victim_skips=sum(v['status']=='ROUTE_ALREADY_ELEVATED' for s in steps for v in s['victim_attempts']),
        second_victim_successes=sum(s.get('second_victim_success',False) for s in moves),
        aborted_steps=sum(s['status']=='ABORTED_CANDIDATE_BUDGET' for s in steps),
        generated_candidates=generated_total,full_neighbor_checks=full_checks,
        candidate_evaluations=used,candidate_budget=budget.candidate_budget,
        budget_exhausted=stop_reason=='CANDIDATE_BUDGET_EXHAUSTED',
        budget_used_up=used>=budget.candidate_budget,
        budget_counts_basic_rejections=budget.budget_counts_basic_rejections,
        generation_failure_cache_enabled=generation_cache_enabled,
        window_slack_mm=float(window_slack_mm),
        generation_cache_records=len(gen_failure_records),
        generation_cache_zero_candidate_records=sum(1 for r in gen_failure_records.values()
            if r['generated_count']==0),
        generation_skip_events=len(generation_skip_events),
        generation_skipped_target_count=len({tuple(e['target_pair']) for e in generation_skip_events}),
        stop_reason=stop_reason,initial_pair_scan_seconds=scan_seconds,
        assignment_seconds=perf_counter()-assignment_started,runtime_seconds=perf_counter()-started,
        baseline_unchanged=True)
    return dict(strategy=strategy,scale=scale,budget_config=budget,routes=routes,steps=steps,curve=curve,
        ledger=ledger,initial_collision_pairs=sorted(initial_pairs),final_collision_pairs=sorted(pairs),
        initial_unresolved_pairs=sorted(initial_uncertain),final_unresolved_pairs=sorted(uncertain),
        elevated_route_ids=sorted(elevated),relocated_route_ids=sorted(relocated),
        generation_skips=generation_skip_events)
