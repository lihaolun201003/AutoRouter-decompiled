"""Bounded fixed-layer experiments. Current routes, one elevation per route."""
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass,asdict
from itertools import combinations
from time import perf_counter
from .models import Point3D
from .geometry_3d import CosineTransition3D
from .clearance_3d import (_box,_box_distance,fixed_z,analyze_primitive_clearance,
    analyze_route3d_clearance)
from .layer_assignment_3d import elevation_candidates,evaluate_elevation


@dataclass
class RouteView:
    route: object
    primitive_boxes: tuple
    box: tuple

    @classmethod
    def prepare(cls,route):
        route.validate()
        if not route.primitives: raise ValueError('EMPTY_ROUTE')
        boxes=tuple(_box(p,0.,1.) for p in route.primitives)
        box=tuple((min(b[k][0] for b in boxes),max(b[k][1] for b in boxes)) for k in range(3))
        return cls(route,boxes,box)


def pair_status(a,b,clearance_mm):
    """9-C classification, short-circuit COLLISION; no minimum-distance request.

    AABB and fixed-z lower bounds only skip pairs proved CLEAR. Other primitive
    pairs use the unchanged 9-C API, with its original default tolerances.
    """
    guard=2e-9
    if _box_distance(a.box,b.box)>=clearance_mm+guard:return 'CLEAR'
    statuses=set()
    for i,p in enumerate(a.route.primitives):
        for j,q in enumerate(b.route.primitives):
            if _box_distance(a.primitive_boxes[i],b.primitive_boxes[j])>=clearance_mm+guard:continue
            zp,zq=fixed_z(p),fixed_z(q)
            if zp is not None and zq is not None and abs(zp-zq)>=clearance_mm+guard:continue
            status=analyze_primitive_clearance(p,q,clearance_mm)['status']
            if status=='COLLISION':return status
            statuses.add(status)
    return next((s for s in ('INVALID_GEOMETRY','DISTANCE_NOT_CONVERGED','AMBIGUOUS_CLEARANCE','TOUCHING_THRESHOLD') if s in statuses),'CLEAR')


def collision_degree(route_id,pairs):return sum(route_id in pair for pair in pairs)


def victim_order(pair,pairs):return sorted(pair,key=lambda r:(collision_degree(r,pairs),r))


def candidate_rank(row):
    c=row['candidate']
    return (row['after_collision_count'],len(row['new_collisions_created']),c.extra_length_mm,
            c.elevated_length_mm,c.rise_window,c.fall_window)


def improving(before,after):return after<before


def _target_points(report,saved_points):
    if saved_points:return deepcopy(saved_points)
    # Clearance-only conflicts may lack an XY CROSS. 9-C supplies actual closest
    # points on the movable (still Layer 0) route as finite-window anchors.
    values=[]
    for r in report['pair_results']:
        if r['status']=='COLLISION':
            p=Point3D(**r['closest_point_a'])
            if p not in values:values.append(p)
    return values


def run_sequential_elevation(initial_routes,config,*,max_targets=30,saved_crossings=None,progress=None):
    """Original Step 9-E entry point and 30-target bound remain unchanged."""
    return _run_sequential_elevation(initial_routes,config,max_targets=max_targets,
        saved_crossings=saved_crossings,progress=progress)


def _run_sequential_elevation(initial_routes,config,*,max_targets=30,saved_crossings=None,progress=None,expanded_layers=False,fixed_1024=False):
    """Every target is the smallest current collision pair not skipped on failure.

    Failed pairs are not retried in this bounded experiment. Candidate rejection
    leaves routes untouched. All candidates for the first available victim are
    evaluated; the second victim is tried only if the first has no improvement.
    """
    if fixed_1024 and (len(initial_routes)!=1024 or not expanded_layers or len(config.layers)!=3):raise ValueError('FIXED_1024_THREE_LAYER_REQUIRED')
    limit=1024 if fixed_1024 else 50 if expanded_layers else 30
    if type(max_targets) is not int or not 1<=max_targets<=limit:raise ValueError(f'TARGET_LIMIT_1_TO_{limit}')
    generate=elevation_candidates;rank=candidate_rank
    if expanded_layers:
        from .three_layer_assignment_3d import candidate_families,layer_candidate_rank
        generate=candidate_families;rank=layer_candidate_rank
    config.validate();started=perf_counter()
    frozen=deepcopy(initial_routes);routes=deepcopy(initial_routes)
    views={i:RouteView.prepare(r) for i,r in routes.items()}
    if any(i!=r.route_id for i,r in routes.items()):raise ValueError('ROUTE_ID_MISMATCH')
    if any(isinstance(p,CosineTransition3D) or p.start.z!=0 or p.end.z!=0 for r in routes.values() for p in r.primitives):
        raise ValueError('INITIAL_LAYER_ZERO_REQUIRED')
    pairs=set();uncertain=set();initial_checks=0;scan_started=perf_counter()
    for a,b in combinations(sorted(routes),2):
        status=pair_status(views[a],views[b],config.clearance_mm);initial_checks+=1
        if status=='COLLISION':pairs.add((a,b))
        elif status!='CLEAR':uncertain.add((a,b))
        if progress and initial_checks%10000==0:progress(dict(phase='INITIAL_COLLISIONS',checked=initial_checks,collisions=len(pairs),seconds=perf_counter()-started))
    scan_seconds=perf_counter()-scan_started;assignment_started=perf_counter()
    initial_pairs=set(pairs);initial_uncertain=set(uncertain)
    elevated=set();skipped=set();steps=[];curve=[dict(step=0,collision_pair_count=len(pairs))]
    if progress:progress(dict(phase='INITIAL_DONE',checked=initial_checks,collisions=len(pairs),uncertain=len(uncertain),seconds=perf_counter()-started))
    while len(steps)<max_targets:
        pending=pairs-skipped
        if not pending:break
        target=min(pending)
        order=victim_order(target,pairs)
        step=dict(step_index=len(steps)+1,target_pair=target,victim_order=order,
            victim_degrees={str(i):collision_degree(i,pairs) for i in order},victim_attempts=[],
            global_collision_pairs_before=len(pairs),elevated_routes_before=sorted(elevated))
        winner=None
        if progress:progress(dict(phase='TARGET_START',step=step['step_index'],target=target,degrees=step['victim_degrees'],seconds=perf_counter()-started))
        for victim_index,moved in enumerate(order):
            va=dict(route_id=moved,priority_index=victim_index,candidates=[])
            step['victim_attempts'].append(va)
            if moved in elevated:
                va['status']='ROUTE_ALREADY_ELEVATED';continue
            other=target[1] if moved==target[0] else target[0]
            target_report=analyze_route3d_clearance(routes[moved],routes[other],config.clearance_mm)
            if target_report['status']!='COLLISION':
                raise AssertionError('Current collision set disagrees with 9-C target analysis')
            points=_target_points(target_report,(saved_crossings or {}).get(target))
            candidates,failure=generate(routes[moved],target,points,config)
            va.update(generated_count=len(candidates),generation_failure=failure)
            old_neighbors={b if a==moved else a for a,b in pairs if moved in (a,b)}
            eligible=[]
            for index,candidate in enumerate(candidates):
                basic=evaluate_elevation(candidate,routes[moved],routes[other],config)
                row=dict(candidate_index=index,basic_status=basic['status'],basic_reasons=basic['reasons'],
                    rise_window=candidate.rise_window,fall_window=candidate.fall_window)
                if expanded_layers:row['target_layer_id']=candidate.layer_to
                va['candidates'].append(row)
                if basic['status']!='ACCEPTED_TARGET_PAIR_ONLY':continue
                cv=RouteView.prepare(candidate.route);after_neighbors=set();unknown=[];after_status={}
                for neighbor in sorted(routes):
                    if neighbor==moved:continue
                    status=pair_status(cv,views[neighbor],config.clearance_mm)
                    after_status[neighbor]=status
                    if status=='COLLISION':after_neighbors.add(neighbor)
                    elif status!='CLEAR':unknown.append(neighbor)
                removed=sorted(old_neighbors-after_neighbors);created=sorted(after_neighbors-old_neighbors)
                row.update(before_collision_count=len(old_neighbors),after_collision_count=len(after_neighbors),
                    old_collisions_removed=removed,new_collisions_created=created,net_collision_reduction=len(removed)-len(created),
                    unresolved_neighbor_ids=unknown,checked_neighbor_count=len(after_status),
                    current_elevated_neighbors_checked=sorted(elevated-{moved}),
                    extra_length_mm=candidate.extra_length_mm,elevated_length_mm=candidate.elevated_length_mm)
                # Keep 9-D's unresolved-neighbor rejection. Never improve a count
                # by treating NOT_CONVERGED or AMBIGUOUS as an established clear.
                row['status']='IMPROVING' if not unknown and improving(len(old_neighbors),len(after_neighbors)) else 'UNRESOLVED_NEIGHBOR' if unknown else 'NOT_IMPROVING'
                if row['status']=='IMPROVING':eligible.append(dict(candidate=candidate,after_status=after_status,**row))
                if progress:progress(dict(phase='CANDIDATE',step=step['step_index'],victim=moved,index=index,total=len(candidates),status=row['status'],after=len(after_neighbors),seconds=perf_counter()-started))
            if eligible:
                winner=min(eligible,key=rank);va['status']='SELECTED';break
            va['status']='NO_IMPROVING_CANDIDATE'
        if winner is None:
            skipped.add(target)
            step['status']='BOTH_ALREADY_ELEVATED' if all(i in elevated for i in target) else 'NO_IMPROVING_SINGLE_ELEVATION'
        else:
            c=winner['candidate'];moved=c.route_id
            routes[moved]=deepcopy(c.route);views[moved]=RouteView.prepare(routes[moved]);elevated.add(moved)
            pairs={p for p in pairs if moved not in p};uncertain={p for p in uncertain if moved not in p}
            for neighbor,status in winner['after_status'].items():
                pair=tuple(sorted((moved,neighbor)))
                if status=='COLLISION':pairs.add(pair)
                elif status!='CLEAR':uncertain.add(pair)
            assert step['global_collision_pairs_before']-len(pairs)==winner['net_collision_reduction']>0
            assert target not in pairs
            step.update(status='ELEVATED',moved_route_id=moved,selected_candidate_index=winner['candidate_index'],
                victim_collision_degree_before=step['victim_degrees'][str(moved)],
                route_collision_count_before=winner['before_collision_count'],route_collision_count_after=winner['after_collision_count'],
                old_collisions_removed=winner['old_collisions_removed'],new_collisions_created=winner['new_collisions_created'],
                net_collision_reduction=winner['net_collision_reduction'],extra_length_mm=c.extra_length_mm,
                transition_count=2,elevated_length_mm=c.elevated_length_mm,
                elevation_geometry=asdict(c),second_victim_success=step['victim_attempts'][-1]['priority_index']==1)
            if expanded_layers:step['target_layer_id']=c.layer_to
            curve.append(dict(step=step['step_index'],collision_pair_count=len(pairs)))
        step['global_collision_pairs_after']=len(pairs);steps.append(step)
        if progress:progress(dict(phase='TARGET_DONE',step=step['step_index'],target=target,status=step['status'],collisions=len(pairs),seconds=perf_counter()-started,steps=steps))
    success=[s for s in steps if s['status']=='ELEVATED']
    assert initial_routes==frozen
    result=dict(routes=routes,steps=steps,collision_history=curve,initial_collision_pairs=sorted(initial_pairs),
        final_collision_pairs=sorted(pairs),initial_unresolved_pairs=sorted(initial_uncertain),final_unresolved_pairs=sorted(uncertain),
        elevated_route_ids=sorted(elevated),initial_collision_pair_count=len(initial_pairs),final_collision_pair_count=len(pairs),
        target_attempts=len(steps),successful_elevations=len(success),skipped_already_clear=0,
        skipped_already_clear_semantics='DYNAMIC_SELECTION_NO_PRECOMPUTED_TARGET_LIST',
        failed_no_candidate=sum(s['status']=='NO_IMPROVING_SINGLE_ELEVATION' for s in steps),
        both_already_elevated=sum(s['status']=='BOTH_ALREADY_ELEVATED' for s in steps),
        already_elevated_victim_skips=sum(v['status']=='ROUTE_ALREADY_ELEVATED' for s in steps for v in s['victim_attempts']),
        second_victim_successes=sum(s['second_victim_success'] for s in success),
        total_extra_length_mm=sum(s['extra_length_mm'] for s in success),runtime_seconds=perf_counter()-started,
        baseline_unchanged=True,stop_reason='TARGET_LIMIT' if len(steps)==max_targets else 'NO_UNSKIPPED_CURRENT_COLLISIONS')
    if fixed_1024:result.update(initial_pair_scan_seconds=scan_seconds,assignment_seconds=perf_counter()-assignment_started)
    return result
