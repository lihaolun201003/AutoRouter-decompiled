"""Step 16 (strategy v3) tests: generation-failure scheduling cache and window slack.

Synthetic fixtures plus two read-only 512 checks. The new switches default to
off, so the historical entry points keep their behaviour; these tests pin both
the new semantics and the default compatibility.
"""
import json
from copy import deepcopy
from math import pi
from pathlib import Path
from src.models import Layer,Point3D
from src.geometry_3d import LineSegment3D,PlanarArcSegment3D,CosineTransition3D,Route3D
from src.geometry_3d_diagnostics import minimum_xy_run_for_radius,analyze_route3d_joins
from src.clearance_3d import analyze_route3d_self_clearance
from src.layer_assignment_3d import elevation_candidates,evaluate_elevation
from src.three_layer_assignment_3d import LayerConfiguration
from src.multi_attribution import deserialize_plot
from src.geometry_3d import lift_smoothed_route_to_layer
from src.strategy_v2_3d import (BudgetConfig,run_strategy_v2,generation_cache_hit,generation_input_key,
    xy_projection_preserved)


def config(n=3):
    return LayerConfiguration([Layer(i,float(i)) for i in range(n)],.1,5.,
        'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC')


def L(a,b):return LineSegment3D(Point3D(*a),Point3D(*b))


def structural_scenario():
    """Three independent targets: two long solvable pairs and one pair (2,3) of
    2 mm routes whose generation always returns zero candidates. Target order
    is (0,1) then (2,3) then (4,5): the structural failure is hit once, a later
    accepted edit bumps the layout version, and only a generation cache can stop
    pair (2,3) from consuming a second formal attempt."""
    routes={0:Route3D(0,[L((-20,.5,0),(20,.5,0))]),1:Route3D(1,[L((0,-20,0),(0,20,0))]),
        2:Route3D(2,[L((30,-1,0),(30,1,0))]),3:Route3D(3,[L((29,0,0),(31,0,0))]),
        4:Route3D(4,[L((60,-20,0),(60,20,0))]),5:Route3D(5,[L((40,5,0),(80,5,0))])}
    crossings={(0,1):[Point3D(0,.5,0)],(2,3):[Point3D(30,0,0)],(4,5):[Point3D(60,5,0)]}
    return routes,crossings


def half_failure_scenario():
    """Route 0 is 2 mm (zero candidates); route 1 is long and can be elevated.
    The target must stay attemptable because only one victim fails."""
    routes={0:Route3D(0,[L((0,-1,0),(0,1,0))]),1:Route3D(1,[L((-20,0,0),(20,0,0))])}
    return routes,{(0,1):[Point3D(0,0,0)]}


def stacking_scenario():
    """Same blocked-pair fixture as the Step 15 tests: the (1,2) failure is
    dynamic (candidates exist but full acceptance fails), so it must keep the
    global-layout-version retry and never be skipped by the generation cache."""
    routes={0:Route3D(0,[L((-20,.05,0),(20,.05,0))]),1:Route3D(1,[L((-6,0,0),(6,0,0))]),
        2:Route3D(2,[L((0,-6,0),(0,6,0))]),3:Route3D(3,[L((10,5,0),(10,11,0))]),
        4:Route3D(4,[L((-20,8,0),(20,8,0))])}
    crossings={(0,1):[Point3D(0,.05,0)],(0,2):[Point3D(0,0,0)],(1,2):[Point3D(0,0,0)],
               (3,4):[Point3D(10,8,0)]}
    return routes,crossings


def boundary_scenario():
    """Arc (R=5) ending tangent into a 100 mm line; crossing at y=50. The
    start-anchored rise window begins exactly 0.1 mm from the arc end, which is
    the recorded SELF_AMBIGUOUS_CLEARANCE pattern."""
    arc=PlanarArcSegment3D(-5,0,0,5,-pi/2,pi/2)
    route=Route3D(3,[L((-15,-5,0),(-5,-5,0)),arc,L((0,0,0),(0,100,0))])
    return route,[Point3D(0,50,0)]


def run_C(routes,crossings,**kwargs):
    return run_strategy_v2(routes,routes,config(3),strategy='C',scale=len(routes),
        saved_crossings=crossings,budget=BudgetConfig(len(routes),10,400,True,'TEST'),**kwargs)


def test_structural_zero_candidates_not_retried_and_skip_not_charged():
    routes,crossings=structural_scenario()
    off=run_C(routes,crossings)
    on=run_C(routes,crossings,generation_failure_cache=True)
    # Historical behaviour: the structural failure is attempted again after the
    # layout changed, consuming a second formal target attempt.
    assert [s['target_pair'] for s in off['steps']]==[(0,1),(2,3),(4,5),(2,3)]
    assert off['ledger']['stop_reason']=='NO_ELIGIBLE_TARGETS'
    assert off['ledger']['generation_skip_events']==0
    # With the cache: the same zero-candidate generation is recognised, the
    # target is skipped without a step, and the attempt bound is not consumed.
    assert [s['target_pair'] for s in on['steps']]==[(0,1),(2,3),(4,5)]
    assert on['ledger']['target_attempts']==3
    assert on['ledger']['generation_skip_events']==1
    assert on['ledger']['generation_skipped_target_count']==1
    assert on['generation_skips'][0]['target_pair']==(2,3)
    assert on['ledger']['final_collision_pair_count']==off['ledger']['final_collision_pair_count']==1
    assert on['ledger']['generation_cache_zero_candidate_records']==2


def test_third_party_change_still_reevaluates_dynamic_failures():
    # Dynamic (non-zero-candidate) failures keep the global layout version cache;
    # enabling both switches must not change the retry sequence.
    routes,crossings=stacking_scenario()
    off=run_C(routes,crossings)
    on=run_C(routes,crossings,generation_failure_cache=True,window_slack_mm=1e-5)
    assert [(tuple(s['target_pair']),s['status']) for s in off['steps']]==[
        ((0,1),'ELEVATED'),((1,2),'NO_ACCEPTABLE_MOVE'),((3,4),'ELEVATED'),((1,2),'NO_ACCEPTABLE_MOVE')]
    assert [s['target_pair'] for s in on['steps']]==[s['target_pair'] for s in off['steps']]
    assert [s['status'] for s in on['steps']]==[s['status'] for s in off['steps']]
    assert on['ledger']['generation_skip_events']==0


def test_generation_input_key_covers_geometry_anchors_layers_and_settings():
    route=Route3D(0,[L((-20,0,0),(20,0,0))])
    points=[Point3D(0,0,0)]
    key=generation_input_key(route,points,config())
    assert generation_input_key(route,[Point3D(0,0,0)],config())==key
    # Actual anchors, frozen planar geometry, layer planes and every generation
    # setting (including the new slack) change the key.
    assert generation_input_key(route,[Point3D(.5,0,0)],config())!=key
    assert generation_input_key(Route3D(0,[L((-20,0,0),(21,0,0))]),points,config())!=key
    assert generation_input_key(route,points,config(2))!=key
    assert generation_input_key(route,points,config(),window_slack_mm=1e-5)!=key
    cache={((0,1),0):dict(key=key,generated_count=0)}
    assert generation_cache_hit(cache,(0,1),0,key)
    assert not generation_cache_hit(cache,(0,1),0,generation_input_key(route,[Point3D(.5,0,0)],config()))
    assert not generation_cache_hit(cache,(0,2),0,key)
    assert not generation_cache_hit(cache,(0,1),1,key)
    # A recorded non-zero candidate list is a dynamic outcome, never a
    # structural failure; a missing record is not a hit either.
    assert not generation_cache_hit({((0,1),0):dict(key=key,generated_count=3)},(0,1),0,key)
    assert not generation_cache_hit({},(0,1),0,key)


def test_one_sided_failure_does_not_block_the_other_victim():
    routes,crossings=half_failure_scenario()
    result=run_C(routes,crossings,generation_failure_cache=True)
    assert len(result['steps'])==1
    step=result['steps'][0]
    assert step['status']=='ELEVATED' and step['moved_route_id']==1
    by_route={v['route_id']:v for v in step['victim_attempts']}
    assert by_route[0]['generated_count']==0
    assert by_route[1]['generated_count']>0
    # Both victims were attempted, nothing was skipped, and the candidate with
    # only one failing side stays a normal attemptable target.
    assert result['ledger']['generation_skip_events']==0
    assert result['ledger']['generation_cache_zero_candidate_records']==1


def test_defaults_preserve_historical_behaviour_and_generation_output():
    routes,crossings=stacking_scenario()
    base=run_C(routes,crossings)
    explicit=run_C(routes,crossings,generation_failure_cache=False,window_slack_mm=0.0)
    assert base['steps']==explicit['steps']
    timings=('runtime_seconds','initial_pair_scan_seconds','assignment_seconds')
    assert {k:v for k,v in base['ledger'].items() if k not in timings}=={
        k:v for k,v in explicit['ledger'].items() if k not in timings}
    assert base['final_collision_pairs']==explicit['final_collision_pairs']
    # A/B never enable the cache even when the flag is passed.
    b=run_strategy_v2(routes,routes,config(3),strategy='B',scale=len(routes),saved_crossings=crossings,
        budget=BudgetConfig(len(routes),10,400,True,'TEST'),generation_failure_cache=True)
    assert b['ledger']['generation_failure_cache_enabled'] is False
    # window_slack_mm=0.0 is byte-identical generation to the default.
    route,points=boundary_scenario()
    a,_=elevation_candidates(route,(3,9),points,config(),target_layer_id=1)
    b2,_=elevation_candidates(route,(3,9),points,config(),target_layer_id=1,window_slack_mm=0.0)
    assert [(c.rise_window,c.fall_window) for c in a]==[(c.rise_window,c.fall_window) for c in b2]


def test_window_slack_moves_boundary_candidate_to_clear_and_keeps_invariants():
    route,points=boundary_scenario()
    base,_=elevation_candidates(route,(3,9),points,config(),target_layer_id=1)
    recorded=[c for c in base if c.rise_window[0]==2 and abs(c.rise_window[1]-.001)<1e-9]
    assert recorded
    # Without slack the start-anchored placement sits exactly on the threshold.
    assert all(analyze_route3d_self_clearance(c.route,.1)['status']!='CLEAR' for c in recorded)
    shifted,_=elevation_candidates(route,(3,9),points,config(),target_layer_id=1,window_slack_mm=1e-5)
    matched=[c for c in shifted if c.rise_window[0]==2 and abs(c.rise_window[1]-.0010001)<1e-6]
    assert matched
    candidate=matched[0]
    self_result=analyze_route3d_self_clearance(candidate.route,.1)
    assert self_result['status']=='CLEAR'
    assert abs(self_result['minimum_distance_mm']-0.1)<=2e-5
    # Endpoints, XY projection, C0/C1 joins and the curvature radius all hold.
    assert candidate.route.start_point==route.start_point and candidate.route.end_point==route.end_point
    ok,reason=xy_projection_preserved(candidate.route,route)
    assert ok,reason
    joins=analyze_route3d_joins(candidate.route)
    assert joins.all_C0 and joins.all_C1_direction
    assert candidate.minimum_radius_mm>=config().required_radius_mm
    other=Route3D(4,[L((-30,50,0),(30,50,0))])
    evaluation=evaluate_elevation(candidate,route,other,config())
    assert not [r for r in evaluation['reasons'] if r.startswith('SELF_')]
    assert 'ENDPOINT_CHANGED' not in evaluation['reasons'] and 'RADIUS_FAILED' not in evaluation['reasons']


def test_true_self_collision_still_rejected_under_slack():
    # Two 0.05 mm parallel legs: a real sub-threshold distance must stay a
    # rejection; the slack only moves window placements, it never reclassifies.
    arc=PlanarArcSegment3D(.025,30,0,.025,pi,pi)
    route=Route3D(9,[L((0,0,0),(0,30,0)),arc,L((.05,30,0),(.05,0,0))])
    assert analyze_route3d_self_clearance(route,.1)['status']=='COLLISION'
    candidates,_=elevation_candidates(route,(9,8),[Point3D(0,15,0)],config(),target_layer_id=1,
        window_slack_mm=1e-5)
    assert candidates
    evaluation=evaluate_elevation(candidates[0],route,Route3D(8,[L((-5,15,0),(5,15,0))]),config())
    assert evaluation['status']=='REJECTED' and 'SELF_COLLISION' in evaluation['reasons']


def test_extra_slack_can_remove_a_just_barely_fitting_window():
    # Honest negative effect: a window that fits by 1.5e-5 mm no longer fits
    # once the pad grows by the slack (2*slack of the straight run).
    run=minimum_xy_run_for_radius(1.,5.)*(1+1e-9)
    length=2*run+.4+3e-5
    route=Route3D(7,[L((0,0,0),(0,length,0))])
    points=[Point3D(0,length/2,0)]
    base,failure=elevation_candidates(route,(7,6),points,config(),target_layer_id=1)
    assert base and failure is None
    shrunk,failure_with_slack=elevation_candidates(route,(7,6),points,config(),target_layer_id=1,
        window_slack_mm=1e-5)
    assert shrunk==[] and failure_with_slack=='INSUFFICIENT_TRANSITION_SPACE'


def test_skips_and_rejections_leave_routes_and_planar_untouched():
    routes,crossings=structural_scenario()
    frozen=deepcopy(routes)
    result=run_C(routes,crossings,generation_failure_cache=True)
    assert routes==frozen
    for i,route in result['routes'].items():
        if any(isinstance(p,CosineTransition3D) for p in route.primitives):
            ok,reason=xy_projection_preserved(route,frozen[i])
            assert ok,reason
    assert result['ledger']['baseline_unchanged'] is True


def test_saved_512_ambiguous_candidates_become_clear_with_slack():
    """Read-only 512 regression: the recorded SELF_AMBIGUOUS_CLEARANCE sample
    (step 2, target (9,34), route 34, layer 1) reproduces with the default
    slack-free generation and becomes CLEAR with the slack, with the window
    count unchanged."""
    root=Path(__file__).parents[1]
    rows=json.loads((root/'outputs/step_8_5_legacy_512_plot_geometry.json').read_text())['routes']
    planar=lift_smoothed_route_to_layer(deserialize_plot(
        next(r for r in rows if r['id']==34)),Layer(0,0))
    crossings=[]
    for text in (root/'outputs/step_8_5_legacy_512_physical_events.jsonl').read_text().splitlines():
        e=json.loads(text)
        if e['kind']=='cross' and tuple(sorted((e['route_a_id'],e['route_b_id'])))==(9,34):
            crossings.append(Point3D(e['point']['x'],e['point']['y'],0))
    assert len(crossings)==2
    base,_=elevation_candidates(planar,(9,34),crossings,config(),target_layer_id=1)
    recorded=[c for c in base if c.rise_window[0]==2 and abs(c.rise_window[1]-.0008067769261799112)<1e-15]
    assert recorded
    assert all(analyze_route3d_self_clearance(c.route,.1)['status']!='CLEAR' for c in recorded)
    shifted,_=elevation_candidates(planar,(9,34),crossings,config(),target_layer_id=1,window_slack_mm=1e-5)
    assert len(shifted)==len(base)   # the slack moves windows, it does not remove any here
    matched=[c for c in shifted if c.rise_window[0]==2 and abs(c.rise_window[1]-.0008068576038725293)<1e-12]
    assert matched
    assert all(analyze_route3d_self_clearance(c.route,.1)['status']=='CLEAR' for c in matched)
