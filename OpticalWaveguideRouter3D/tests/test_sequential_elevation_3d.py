from copy import deepcopy
from types import SimpleNamespace
from src.models import Layer,Point3D
from src.geometry_3d import LineSegment3D,Route3D
from src.layer_assignment_3d import LayerConfiguration,elevation_candidates
from src.clearance_3d import analyze_route3d_clearance
from src.sequential_elevation_3d import (RouteView,pair_status,collision_degree,victim_order,
    improving,candidate_rank,run_sequential_elevation)

def config():return LayerConfiguration([Layer(0,0),Layer(1,1)],.1,5.,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC')
def line(a,b):return LineSegment3D(Point3D(*a),Point3D(*b))
def fixture():return {0:Route3D(0,[line((-20,0,0),(20,0,0))]),1:Route3D(1,[line((0,-20,0),(0,20,0))])}
def run():return run_sequential_elevation(fixture(),config(),max_targets=1)

def test_current_degree_and_victim_order():
    pairs={(0,1),(0,2),(2,3)}
    assert collision_degree(0,pairs)==2 and victim_order((0,1),pairs)==[1,0]
    assert victim_order((0,2),pairs)==[0,2]

def test_strict_decrease_only():assert improving(3,2) and not improving(3,3) and not improving(3,4)

def test_candidate_lexicographic_rank():
    c=SimpleNamespace(extra_length_mm=1.,elevated_length_mm=2.,rise_window=(0,.1,.2),fall_window=(0,.8,.9))
    a=dict(candidate=c,after_collision_count=2,new_collisions_created=[1])
    b=dict(candidate=c,after_collision_count=3,new_collisions_created=[])
    assert candidate_rank(a)<candidate_rank(b)
    b['after_collision_count']=2
    assert candidate_rank(b)<candidate_rank(a)

def test_successful_replacement_and_global_update():
    r=run();assert r['successful_elevations']==1 and r['initial_collision_pair_count']==1 and r['final_collision_pair_count']==0
    assert r['steps'][0]['net_collision_reduction']==1 and len(r['elevated_route_ids'])==1
    i=r['elevated_route_ids'][0];assert len(r['routes'][i].primitives)==5

def test_failed_candidate_leaves_routes_unchanged():
    routes={0:Route3D(0,[line((-1,0,0),(1,0,0))]),1:Route3D(1,[line((0,-1,0),(0,1,0))])}
    old=deepcopy(routes);r=run_sequential_elevation(routes,config(),max_targets=1)
    assert r['successful_elevations']==0 and r['routes']==routes==old and r['failed_no_candidate']==1

def test_current_elevated_geometry_changes_collision_answer():
    routes=fixture();cs,_=elevation_candidates(routes[0],(0,1),[Point3D(0,0,0)],config())
    other=RouteView.prepare(routes[1])
    assert pair_status(RouteView.prepare(routes[0]),other,.1)=='COLLISION'
    assert pair_status(RouteView.prepare(cs[0].route),other,.1)=='CLEAR'

def test_classifier_matches_9c():
    routes=fixture();cs,_=elevation_candidates(routes[0],(0,1),[Point3D(0,0,0)],config())
    for a in [routes[0],cs[0].route]:
        for z in (0.,.5,1.,2.):
            b=Route3D(4,[line((0,-20,z),(0,20,z))])
            assert pair_status(RouteView.prepare(a),RouteView.prepare(b),.1)==analyze_route3d_clearance(a,b,.1)['status']

def test_deterministic_replay():
    a,b=run(),run()
    assert a['steps']==b['steps'] and a['routes']==b['routes'] and a['final_collision_pairs']==b['final_collision_pairs']

def test_target_stopping_rule():
    routes=fixture();routes[2]=Route3D(2,[line((-20,1,0),(20,1,0))])
    r=run_sequential_elevation(routes,config(),max_targets=1)
    assert r['target_attempts']==1 and r['stop_reason']=='TARGET_LIMIT'
    try:run_sequential_elevation(routes,config(),max_targets=31)
    except ValueError:pass
    else:raise AssertionError('Exceeded experiment limit')

def test_baseline_read_only():
    routes=fixture();old=deepcopy(routes);r=run_sequential_elevation(routes,config(),max_targets=1)
    assert routes==old and r['baseline_unchanged']

def test_later_candidates_check_current_elevated_neighbor():
    routes=fixture();routes[2]=Route3D(2,[line((-20,1,0),(20,1,0))])
    r=run_sequential_elevation(routes,config(),max_targets=2)
    assert len(r['steps'])==2
    rows=[c for v in r['steps'][1]['victim_attempts'] for c in v['candidates'] if 'current_elevated_neighbors_checked' in c]
    assert rows and all(0 in c['current_elevated_neighbors_checked'] for c in rows)

def test_already_elevated_fallback():
    # Equal initial degrees make 0 move first. Its port conflict with 2 remains.
    routes=fixture();routes[2]=Route3D(2,[line((-19.99,-.02,0),(-19.99,.02,0))])
    routes[3]=Route3D(3,[line((-.02,10,0),(.02,10,0))])
    r=run_sequential_elevation(routes,config(),max_targets=2)
    assert r['steps'][0]['moved_route_id']==0
    second=r['steps'][1]['victim_attempts']
    assert second[0]['route_id']==0 and second[0]['status']=='ROUTE_ALREADY_ELEVATED'
    assert second[1]['route_id']==2 and second[1]['status']=='NO_IMPROVING_CANDIDATE'
    routes=fixture();routes[0]=Route3D(0,[line((-1,0,0),(1,0,0))])
    r=run_sequential_elevation(routes,config(),max_targets=1)
    assert r['steps'][0]['moved_route_id']==1 and r['steps'][0]['second_victim_success']
