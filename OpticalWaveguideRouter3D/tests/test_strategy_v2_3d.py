"""Step 15 tests: shared A/B/C engine, full acceptance, ledgers and caches.

Synthetic fixtures only; the 512/1024 experiments are separate drivers.
"""
import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from src.models import Layer,Point3D
from src.geometry_3d import LineSegment3D,CosineTransition3D,Route3D
from src.layer_assignment_3d import elevation_candidates
from src.three_layer_assignment_3d import LayerConfiguration
from src.sequential_elevation_3d import RouteView,pair_status
from src.strategy_v2_3d import (BudgetConfig,FROZEN_BUDGETS,frozen_budget,run_strategy_v2,
    run_fixed_target_diagnostic,failure_cache_hit,route_layer,strategy_rank,target_priority,
    route_degrees,xy_projection_preserved,full_acceptance,xy_polyline_length)


def config(n=3):
    return LayerConfiguration([Layer(i,float(i)) for i in range(n)],.1,5.,
        'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC')


def L(a,b):return LineSegment3D(Point3D(*a),Point3D(*b))


def mixed():
    """X (long horizontal), Y (12 mm vertical, layer-1 only), W1..W6 (long
    verticals crossing X), Z1..Z4 (short horizontals crossing Y only)."""
    routes={0:Route3D(0,[L((-20,0,0),(20,0,0))]),1:Route3D(1,[L((0,-6,0),(0,6,0))])}
    for k,x in enumerate((-10,-7,-4,4,7,10)):
        routes[2+k]=Route3D(2+k,[L((x,-20,0),(x,20,0))])
    for k,y in enumerate((-1,-.5,.5,1)):
        routes[8+k]=Route3D(8+k,[L((-3,y,0),(3,y,0))])
    return routes


def simple_pq():
    """P crosses Q and R; moving P clears two pairs, moving Q clears one."""
    return {0:Route3D(0,[L((-20,0,0),(20,0,0))]),
            1:Route3D(1,[L((0,-20,0),(0,20,0))]),
            2:Route3D(2,[L((5,-20,0),(5,20,0))])}


def crossings_for(name):
    if name=='mixed':
        out={(0,1):[Point3D(0,0,0)]}
        for k,x in enumerate((-10,-7,-4,4,7,10)):out[(0,2+k)]=[Point3D(x,0,0)]
        for k,y in enumerate((-1,-.5,.5,1)):out[(1,8+k)]=[Point3D(0,y,0)]
        return out
    if name=='pq':return {(0,1):[Point3D(0,0,0)],(0,2):[Point3D(5,0,0)]}
    raise ValueError(name)


def routes_for(name):return mixed() if name=='mixed' else simple_pq()


@lru_cache(maxsize=None)
def run_cached(name,layers,strategy,max_targets=30,budget=400):
    routes=routes_for(name);scale=len(routes)
    result=run_strategy_v2(routes,routes,config(layers),strategy=strategy,scale=scale,
        saved_crossings=crossings_for(name),
        budget=BudgetConfig(scale,max_targets,budget,True,'TEST_FIXTURE'))
    return result


def test_frozen_budgets_match_saved_history_rows():
    root=Path(__file__).parents[1]
    rows=json.loads((root/'outputs/step_9_f_three_layer_attempts.json').read_text())
    measured=sum(len(v['candidates']) for s in rows for v in s['victim_attempts'])
    assert measured==FROZEN_BUDGETS[512].candidate_budget
    rows=json.loads((root/'outputs/step_10_fixed_1024_attempts.json').read_text())
    measured=sum(len(v['candidates']) for s in rows for v in s['victim_attempts'])
    assert measured==FROZEN_BUDGETS[1024].candidate_budget
    assert frozen_budget(512).max_targets==50 and frozen_budget(1024).max_targets==1024


def test_budget_must_count_basic_rejections():
    try:BudgetConfig(10,5,5,False,'TEST').validate()
    except ValueError as ex:assert 'BUDGET_MUST_COUNT_BASIC_REJECTIONS' in str(ex)
    else:raise AssertionError('expected rejection of non-counting budget')


def test_target_priority_prefers_conflict_concentration():
    pairs={(0,1),(0,2),(1,2),(2,3)}
    degrees=route_degrees(pairs)
    assert degrees[2]==3 and degrees[3]==1
    assert min(pairs,key=lambda p:target_priority(p,degrees))==(0,2)
    assert target_priority((1,2),degrees)<target_priority((2,3),degrees)


class _FakeCandidate:
    def __init__(self,layer_to,rise_window=(0,0.,0.),fall_window=(1,0.,0.),elevated_length_mm=10.):
        self.layer_to=layer_to;self.rise_window=rise_window;self.fall_window=fall_window
        self.elevated_length_mm=elevated_length_mm


def _rank_row(net,created,delta,victim=0,layer=1):
    return dict(candidate=_FakeCandidate(layer),net_collision_reduction=net,
        new_collisions_created=created,step_length_delta_mm=delta,transition_count=2,victim_id=victim)


def test_strategy_rank_net_reduction_before_after_count():
    # A row with MORE created pairs still wins on a larger net reduction.
    better=_rank_row(3,[7,8,9],.2,victim=5)
    worse=_rank_row(2,[9],.1,victim=1)
    assert min([better,worse],key=strategy_rank) is better
    # Equal net: fewer created pairs wins.
    assert min([_rank_row(2,[1,2],.1),_rank_row(2,[1],.2)],key=strategy_rank)['new_collisions_created']==[1]
    # Equal net and creations: smaller length cost wins.
    assert min([_rank_row(2,[],.3),_rank_row(2,[],.05)],key=strategy_rank)['step_length_delta_mm']==.05


def test_b_compares_both_victims_a_stops_at_first():
    a=run_cached('pq',3,'A');b=run_cached('pq',3,'B')
    assert [s.get('moved_route_id') for s in a['steps']]==[1,0]
    assert [s.get('moved_route_id') for s in b['steps']]==[0]
    assert b['steps'][0]['net_collision_reduction']==2
    assert a['steps'][0]['net_collision_reduction']==1


def test_b_filters_immovable_target_c_relocates():
    b=run_cached('mixed',3,'B');c=run_cached('mixed',3,'C')
    # B drops the (0,1) target once both routes are elevated: three attempts only.
    assert [s['target_pair'] for s in b['steps']]==[(0,1),(1,8),(1,9)]
    assert b['ledger']['final_collision_pair_count']==1
    assert b['ledger']['stop_reason']=='NO_ELIGIBLE_TARGETS'
    # C keeps the target and resolves it by relocating an already-elevated route.
    assert [s['target_pair'] for s in c['steps']]==[(0,1),(1,8),(1,9),(0,1)]
    assert c['ledger']['final_collision_pair_count']==0
    assert c['relocated_route_ids']==[0]
    relocations=[s for s in c['steps'] if s['status']=='RELOCATED']
    assert len(relocations)==1
    assert relocations[0]['target_pair']==(0,1) and relocations[0]['target_layer_id']==2


def test_relocation_keeps_endpoints_xy_and_single_pair_structure():
    planar=mixed();c=run_cached('mixed',3,'C')
    for i,route in c['routes'].items():
        assert route.route_id==i
        assert route.start_point==planar[i].start_point and route.end_point==planar[i].end_point
        ok,reason=xy_projection_preserved(route,planar[i])
        assert ok,reason
        assert sum(isinstance(p,CosineTransition3D) for p in route.primitives) in (0,2)
    relocated=c['routes'][0]
    transitions=[p for p in relocated.primitives if isinstance(p,CosineTransition3D)]
    assert route_layer(relocated)==2
    assert len(transitions)==2 and [p.delta_z for p in transitions]==[2,-2]


def test_touching_threshold_is_not_clear_and_rejection_is_read_only():
    # A flat pair at exactly the threshold classifies as TOUCHING, never CLEAR.
    from src.clearance_3d import analyze_primitive_clearance
    flat=analyze_primitive_clearance(L((0,0,1),(10,0,1)),L((-6,.1,1),(6,.1,1)),.1)
    assert flat['status']=='TOUCHING_THRESHOLD'
    planar=mixed();routes=deepcopy(planar)
    candidates,_=elevation_candidates(planar[0],(0,1),[Point3D(0,0,0)],config(),target_layer_id=1)
    candidate=candidates[0]
    raised_neighbor=Route3D(1,[L((-6,.1,1),(6,.1,1))])
    views={i:RouteView.prepare(r) for i,r in routes.items()}
    views[1]=RouteView.prepare(raised_neighbor)
    # The candidate also has sloped transitions near the neighbor, so the pair
    # classifier reports a boundary state: any of them must block acceptance.
    assert pair_status(RouteView.prepare(candidate.route),views[1],.1) in ('TOUCHING_THRESHOLD','AMBIGUOUS_CLEARANCE')
    frozen=(deepcopy(routes),deepcopy(planar))
    row,after_status=full_acceptance(candidate,0,planar[0],planar[0].total_length(),
        views,{1},config())
    assert row['status']=='REJECTED_FULL' and 'UNRESOLVED_NEIGHBOR' in row['full_reasons']
    assert after_status[1]!='CLEAR'
    assert (routes,planar)==frozen


def test_rejected_candidates_leave_engine_state_unchanged():
    routes=mixed();frozen={i:deepcopy(r) for i,r in routes.items()}
    result=run_strategy_v2(routes,routes,config(2),strategy='C',scale=len(routes),
        saved_crossings=crossings_for('mixed'),budget=BudgetConfig(len(routes),30,400,True,'TEST'))
    assert routes==frozen
    # The two-layer run cannot relocate to another layer, so the final (0,1)
    # attempt must contain candidates rejected by the full acceptance.
    rejected=[row for s in result['steps'] for v in s['victim_attempts'] for row in v['candidates']
        if row['status'] in ('BASIC_REJECTED','REJECTED_FULL')]
    assert rejected
    assert all(row['status'] in ('BASIC_REJECTED','REJECTED_FULL') for row in rejected)
    for s in result['steps']:
        if s['status']=='ABORTED_CANDIDATE_BUDGET':assert 'moved_route_id' not in s


def test_length_ledger_matches_terminal_geometry():
    for name in ('mixed','pq'):
        for strategy in ('A','B','C'):
            result=run_cached(name,3,strategy);ledger=result['ledger']
            assert abs(ledger['final_extra_length_mm']-ledger['total_step_length_delta_mm'])<1e-9
            assert abs(ledger['final_total_length_mm']-ledger['initial_total_length_mm']
                -ledger['final_extra_length_mm'])<1e-9
            moves=[s for s in result['steps'] if s['status'] in ('ELEVATED','RELOCATED')]
            assert abs(sum(s['step_length_delta_mm'] for s in moves)-ledger['final_extra_length_mm'])<1e-9
    relocation=[s for s in run_cached('mixed',3,'C')['steps'] if s['status']=='RELOCATED'][0]
    assert relocation['step_length_delta_mm']>0
    assert relocation['step_length_delta_mm']<relocation['extra_length_mm_vs_planar']


def test_budget_boundary_stops_without_partial_submission():
    routes=mixed()
    result=run_strategy_v2(routes,routes,config(),strategy='B',scale=len(routes),
        saved_crossings=crossings_for('mixed'),budget=BudgetConfig(len(routes),30,5,True,'TEST'))
    ledger=result['ledger']
    assert ledger['candidate_evaluations']<=5
    assert ledger['stop_reason']=='CANDIDATE_BUDGET_EXHAUSTED'
    total_net=sum(s['net_collision_reduction'] for s in result['steps']
        if s['status'] in ('ELEVATED','RELOCATED'))
    assert ledger['final_collision_pair_count']==ledger['initial_collision_pair_count']-total_net
    for s in result['steps']:
        if s['status']=='ABORTED_CANDIDATE_BUDGET':assert 'moved_route_id' not in s


def test_failure_cache_invalidation_and_no_repeat_attempt():
    # Global layout version: any accepted edit anywhere invalidates a cached
    # failure, including edits to third-party routes.
    cache={(0,1):5}
    assert failure_cache_hit(cache,(0,1),5)
    assert not failure_cache_hit(cache,(0,1),6)
    two_layer=run_cached('mixed',2,'C')
    assert [(s['target_pair'],s['status']) for s in two_layer['steps']]==[
        ((0,1),'ELEVATED'),((1,8),'NO_ACCEPTABLE_MOVE'),((1,9),'ELEVATED'),((0,1),'NO_ACCEPTABLE_MOVE')]
    assert two_layer['ledger']['stop_reason']=='NO_ELIGIBLE_TARGETS'
    assert two_layer['ledger']['final_collision_pair_count']==1


def stacking_scenario():
    """B/C short pair blocked by an already-elevated route A; a later edit to the
    third-party pair D/E bumps the layout version and must re-enable B/C, whose
    own two routes were never touched."""
    routes={
        0:Route3D(0,[L((-20,.05,0),(20,.05,0))]),   # A: long, elevated on layer 1 first
        1:Route3D(1,[L((-6,0,0),(6,0,0))]),         # B: short, blocked by A on layer 1
        2:Route3D(2,[L((0,-6,0),(0,6,0))]),         # C: short, blocked by A on layer 1
        3:Route3D(3,[L((10,5,0),(10,11,0))]),       # D: too short to elevate
        4:Route3D(4,[L((-20,8,0),(20,8,0))]),       # E: long, independent pair with D
    }
    crossings={(0,1):[Point3D(0,.05,0)],(0,2):[Point3D(0,0,0)],(1,2):[Point3D(0,0,0)],
               (3,4):[Point3D(10,8,0)]}
    return routes,crossings


def test_third_party_change_reenables_failed_target_and_no_repeat_without_change():
    routes,crossings=stacking_scenario()
    result=run_strategy_v2(routes,routes,config(3),strategy='C',scale=len(routes),
        saved_crossings=crossings,budget=BudgetConfig(len(routes),30,400,True,'TEST'))
    steps=result['steps']
    assert [s['target_pair'] for s in steps]==[(0,1),(1,2),(3,4),(1,2)]
    # First step: A selected although B was attempted too -> not a second victim.
    assert steps[0]['moved_route_id']==0
    assert steps[0]['selected_victim_priority_index']==0
    assert steps[0]['second_victim_success'] is False
    # The third-party pair D/E is resolved by elevating E, bumping the layout
    # version; the blocked B/C target is then retried (second attempt) even
    # though neither B nor C changed.
    assert steps[2]['status']=='ELEVATED' and steps[2]['moved_route_id']==4
    assert steps[3]['target_pair']==(1,2) and steps[3]['status']=='NO_ACCEPTABLE_MOVE'
    # No further attempt once the layout stops changing.
    assert len(steps)==4 and result['ledger']['stop_reason']=='NO_ELIGIBLE_TARGETS'
    assert result['ledger']['final_collision_pair_count']==1


def test_second_victim_field_matches_selected_attempt_in_every_step():
    for name,layers in (('mixed',3),('pq',3),('mixed',2)):
        for strategy in 'ABC':
            result=run_cached(name,layers,strategy)
            for s in result['steps']:
                if s['status'] not in ('ELEVATED','RELOCATED'):continue
                selected=next(va for va in s['victim_attempts'] if va.get('status')=='SELECTED')
                assert s['selected_victim_priority_index']==selected['priority_index']
                assert s['second_victim_success']==(selected['priority_index']==1)


def test_fixed_target_diagnostic_mode_d_vs_e():
    planar,crossings=stacking_scenario()
    # Start state: A and B are both already elevated on layer 1 and collide with
    # each other; the D/E pair is an extra independent target.
    cs_a,_=elevation_candidates(planar[0],(0,1),[Point3D(0,.05,0)],config(3),target_layer_id=1)
    cs_b,_=elevation_candidates(planar[1],(1,2),[Point3D(0,0,0)],config(3),target_layer_id=1)
    start={i:deepcopy(r) for i,r in planar.items()}
    start[0]=cs_a[0].route
    start[1]=cs_b[0].route
    assert route_layer(start[0])==1 and route_layer(start[1])==1
    targets=[(0,1),(3,4)]
    results={}
    for mode in ('D','E'):
        result=run_fixed_target_diagnostic(start,planar,config(3),targets=targets,mode=mode,
            scale=len(start),saved_crossings=crossings,
            budget=BudgetConfig(len(start),30,200,True,'TEST'))
        results[mode]=result
        assert result['ledger']['initial_elevated_route_count']==2
    assert results['D']['ledger']['initial_collision_pair_count']==results['E']['ledger']['initial_collision_pair_count']
    # D may not touch the elevated routes: the both-elevated target is unmovable.
    assert results['D']['ledger']['relocation_victim_attempts']==0
    assert results['D']['steps'][0]['target_pair']==(0,1)
    assert results['D']['steps'][0]['status']=='NO_MOVABLE_ROUTE'
    # E evaluates relocation candidates for the same frozen target list.
    assert results['E']['ledger']['relocation_victim_attempts']>=1
    assert results['E']['ledger']['relocations']>=1
    assert (results['E']['ledger']['final_collision_pair_count']
            < results['D']['ledger']['final_collision_pair_count'])


def test_xy_check_detects_projection_changes():
    planar=Route3D(0,[L((0,0,0),(10,0,0))])
    assert xy_projection_preserved(Route3D(0,[L((0,0,0),(10,0,0))]),planar)==(True,None)
    ok,reason=xy_projection_preserved(Route3D(0,[L((0,.01,0),(10,.01,0))]),planar)
    assert not ok and reason=='XY_SAMPLE_OFF_PLANAR'
    ok,reason=xy_projection_preserved(Route3D(0,[L((0,0,0),(11,0,0))]),planar)
    assert not ok and reason=='XY_TOTAL_LENGTH_CHANGED'


def test_route_layer_and_xy_length_helpers():
    planar=mixed();c=run_cached('mixed',3,'C')
    assert route_layer(planar[2])==0
    assert route_layer(c['routes'][0])==2 and route_layer(c['routes'][1])==1
    assert abs(xy_polyline_length(planar[0])-40.)<1e-12
    assert abs(xy_polyline_length(c['routes'][0])-40.)<1e-12
