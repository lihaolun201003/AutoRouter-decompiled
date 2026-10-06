from copy import deepcopy
from dataclasses import replace
from math import pi,sqrt
from src.models import Layer,Point3D
from src.geometry_3d import LineSegment3D,Route3D,CosineTransition3D
from src.geometry_3d_diagnostics import minimum_xy_run_for_radius,analyze_route3d_joins
from src.sequential_elevation_3d import RouteView,pair_status,run_sequential_elevation
from src.three_layer_assignment_3d import LayerConfiguration,candidate_families,layer_candidate_rank,run_layer_assignment_probe

def config(n=3):return LayerConfiguration([Layer(i,float(i)) for i in range(n)],.1,5.,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC')
def line(a,b):return LineSegment3D(Point3D(*a),Point3D(*b))
def fixture():return {0:Route3D(0,[line((-20,0,0),(20,0,0))]),1:Route3D(1,[line((0,-20,0),(0,20,0))])}
def families(route=None):
    r=route or fixture()[0];return candidate_families(r,(0,1),[Point3D(0,0,0)],config())[0]
def high():return next(c for c in families() if c.layer_to==2)
def raises(fn,word):
    try:fn()
    except ValueError as ex:assert word in str(ex)
    else:raise AssertionError('Expected invalid configuration')

def test_three_layer_configuration():assert [l.z for l in config().layers]==[0,1,2]
def test_duplicate_layer_id_and_z():
    args=(.1,5.,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC')
    raises(lambda:LayerConfiguration([Layer(0,0),Layer(1,1),Layer(1,2)],*args),'DUPLICATE_LAYER_ID')
    raises(lambda:LayerConfiguration([Layer(0,0),Layer(1,1),Layer(2,1)],*args),'DUPLICATE_LAYER_Z')
def test_four_layers_rejected():raises(lambda:config(4),'TWO_OR_THREE')
def test_layer_two_run_formula():
    assert abs(minimum_xy_run_for_radius(2,5)-pi*sqrt(5))<1e-12
    assert high().transition_run_mm>=minimum_xy_run_for_radius(2,5)
def test_zero_two_zero_geometry():
    c=high();ts=[p for p in c.route.primitives if isinstance(p,CosineTransition3D)]
    assert len(ts)==2 and [p.delta_z for p in ts]==[2,-2] and c.layer_to==2
    assert analyze_route3d_joins(c.route).all_C1_direction
def test_layer_two_endpoints_and_radius():
    c=high();original=fixture()[0]
    assert c.route.start_point==original.start_point and c.route.end_point==original.end_point
    assert c.minimum_radius_mm>=5 and c.elevated_start.z==c.elevated_end.z==2
def test_both_families_enumerated():
    cs=families();assert sum(c.layer_to==1 for c in cs)==9 and sum(c.layer_to==2 for c in cs)==9
def test_equal_outcome_prefers_lower_layer():
    c=high();low=replace(c,layer_to=1)
    a=dict(candidate=c,after_collision_count=0,new_collisions_created=[])
    b=dict(candidate=low,after_collision_count=0,new_collisions_created=[])
    assert min([a,b],key=layer_candidate_rank)['candidate'].layer_to==1
def test_better_outcome_selects_layer_two():
    cs=families();a=dict(candidate=cs[0],after_collision_count=2,new_collisions_created=[])
    b=dict(candidate=high(),after_collision_count=1,new_collisions_created=[3])
    assert min([a,b],key=layer_candidate_rank)['candidate'].layer_to==2
def test_layer_one_neighbor_in_layer_two_clearance():
    a=RouteView.prepare(high().route)
    neighbor=next(c for c in families(fixture()[1]) if c.layer_to==1).route
    assert pair_status(a,RouteView.prepare(neighbor),.1)=='CLEAR'
def test_layer_two_neighbor_in_layer_one_clearance():
    a=RouteView.prepare(families()[0].route)
    neighbor=next(c for c in families(fixture()[1]) if c.layer_to==2).route
    assert pair_status(a,RouteView.prepare(neighbor),.1)=='CLEAR'
def test_complete_family_evaluation_and_single_elevation():
    r=run_layer_assignment_probe(fixture(),config(),max_targets=2)
    rows=r['steps'][0]['victim_attempts'][0]['candidates']
    assert {c['target_layer_id'] for c in rows}=={1,2}
    assert all('checked_neighbor_count' in c for c in rows if c['basic_status']=='ACCEPTED_TARGET_PAIR_ONLY')
    assert r['successful_elevations']==len(set(r['elevated_route_ids']))==1
def test_fifty_target_limit():
    assert run_layer_assignment_probe(fixture(),config(),max_targets=50)['successful_elevations']==1
    raises(lambda:run_layer_assignment_probe(fixture(),config(),max_targets=51),'TARGET_LIMIT')
def test_same_baseline_two_and_three_read_only():
    routes=fixture();before=deepcopy(routes)
    a=run_layer_assignment_probe(routes,config(2),max_targets=1)
    b=run_layer_assignment_probe(routes,config(3),max_targets=1)
    assert a['initial_collision_pairs']==b['initial_collision_pairs'] and routes==before
def test_two_layer_control_matches_legacy_algorithm():
    a=run_sequential_elevation(fixture(),config(2),max_targets=1)
    b=run_layer_assignment_probe(fixture(),config(2),max_targets=1)
    assert a['routes']==b['routes'] and a['final_collision_pairs']==b['final_collision_pairs']
    assert a['steps'][0]['elevation_geometry']==b['steps'][0]['elevation_geometry']
def test_three_layer_deterministic_replay():
    a=run_layer_assignment_probe(fixture(),config(),max_targets=1)
    b=run_layer_assignment_probe(fixture(),config(),max_targets=1)
    assert a['steps']==b['steps'] and a['routes']==b['routes']
