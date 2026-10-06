from copy import deepcopy
from math import pi,sqrt
from src.models import Layer,Point3D
from src.geometry_3d import LineSegment3D,Route3D,CosineTransition3D,PlanarArcSegment3D
from src.layer_assignment_3d import (LayerConfiguration,elevation_candidates,build_elevation_candidate,
    evaluate_elevation,probe_single_route_elevation)
from src.geometry_3d_diagnostics import minimum_xy_run_for_radius,analyze_route3d_joins

def config(): return LayerConfiguration([Layer(0,0),Layer(1,1)],.1,5.,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC')
def line(a,b): return LineSegment3D(Point3D(*a),Point3D(*b))
def fixture():
    return Route3D(1,[line((-20,0,0),(20,0,0))]),Route3D(2,[line((0,-20,0),(0,20,0))]),[Point3D(0,0,0)]
def candidate():
    a,b,cross=fixture();return elevation_candidates(b,(2,1),cross,config())[0][0],b,a
def raises(fn,match):
    try:fn()
    except ValueError as ex:assert match in str(ex)
    else:raise AssertionError('Expected ValueError')

def test_configuration_two_layers(): assert len(config().layers)==2
def test_configuration_duplicate_id(): raises(lambda:LayerConfiguration([Layer(0,0),Layer(0,1)],.1,5,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC'),'DUPLICATE_LAYER_ID')
def test_configuration_duplicate_z(): raises(lambda:LayerConfiguration([Layer(0,0),Layer(1,0)],.1,5,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC'),'DUPLICATE_LAYER_Z')
def test_configuration_three_layers_rejected(): raises(lambda:LayerConfiguration([Layer(0,0),Layer(1,1),Layer(2,2)],.1,5,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC'),'EXACTLY_TWO')
def test_configuration_clearance_invalid(): raises(lambda:LayerConfiguration([Layer(0,0),Layer(1,1)],0,5,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC'),'POSITIVE_EXPLICIT')
def test_configuration_radius_invalid(): raises(lambda:LayerConfiguration([Layer(0,0),Layer(1,1)],.1,-1,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC'),'POSITIVE_EXPLICIT')
def test_configuration_experimental_required(): raises(lambda:LayerConfiguration([Layer(0,0),Layer(1,1)],.1,5,'LINE_ONLY_FINITE_WINDOWS','FINAL'),'EXPERIMENTAL')
def test_configuration_policy_invalid(): raises(lambda:LayerConfiguration([Layer(0,0),Layer(1,1)],.1,5,'ARC_CUT','EXPERIMENTAL_SYNTHETIC'),'POLICY')
def test_configuration_input_copied():
    layers=[Layer(0,0),Layer(1,1)];c=LayerConfiguration(layers,.1,5,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC');layers.clear();assert len(c.layers)==2
def test_transition_run_formula(): assert abs(minimum_xy_run_for_radius(1,5)-pi*sqrt(2.5))<1e-12
def test_sufficient_windows():
    a,b,cross=fixture();cs,f=elevation_candidates(b,(2,1),cross,config());assert len(cs)==9 and f is None
def test_insufficient_windows():
    b=Route3D(2,[line((0,-1,0),(0,1,0))]);assert elevation_candidates(b,(2,1),[Point3D(0,0,0)],config())[1]=='INSUFFICIENT_TRANSITION_SPACE'
def test_no_valid_window():
    a,b,cross=fixture();assert elevation_candidates(b,(2,1),[b.start_point],config())[1]=='NO_VALID_TRANSITION_WINDOW'
def test_unknown_crossing_rejected():
    a,b,cross=fixture();raises(lambda:elevation_candidates(b,(2,1),[Point3D(3,3,0)],config()),'NOT_ON_ROUTE')
def test_endpoint_invariant():
    c,b,a=candidate();assert c.route.start_point==b.start_point and c.route.end_point==b.end_point
def test_rise_and_fall():
    c,b,a=candidate();ts=[p for p in c.route.primitives if isinstance(p,CosineTransition3D)];assert len(ts)==2 and ts[0].delta_z==1 and ts[1].delta_z==-1
def test_elevated_fixed_z():
    c,b,a=candidate();assert c.route.primitives[2].start.z==1 and c.route.primitives[2].end.z==1
def test_c0_continuity(): assert analyze_route3d_joins(candidate()[0].route).all_C0
def test_c1_direction(): assert analyze_route3d_joins(candidate()[0].route).all_C1_direction
def test_required_radius(): assert candidate()[0].minimum_radius_mm>=5
def test_target_removed():
    c,b,a=candidate();r=evaluate_elevation(c,b,a,config());assert r['target_after']['status']=='CLEAR' and r['target_collision_removed']
def test_self_clearance():
    c,b,a=candidate();assert evaluate_elevation(c,b,a,config())['self_clearance']['status']=='CLEAR'
def test_synthetic_probe():
    a,b,cross=fixture();r=probe_single_route_elevation(b,a,cross,config());assert r['accepted_count']>0
def test_read_only():
    a,b,cross=fixture();before=deepcopy((a,b,cross));probe_single_route_elevation(b,a,cross,config());assert (a,b,cross)==before
def test_deterministic_failure():
    b=Route3D(2,[line((0,-1,0),(0,1,0))]);args=(b,(2,1),[Point3D(0,0,0)],config());assert elevation_candidates(*args)==elevation_candidates(*args)
def test_length_overhead_positive(): assert candidate()[0].extra_length_mm>0
def test_xy_geometry_preserved():
    c,b,a=candidate()
    for p in c.route.primitives:
        assert p.start.x==0 and p.end.x==0 and p.start.y<p.end.y
def test_no_false_global_claim():
    c,b,a=candidate();r=evaluate_elevation(c,b,a,config());assert r['new_collisions_created'] is None and r['local_validation_status']=='NOT_PERFORMED'
def test_short_manual_window_rejected():
    a,b,cross=fixture();raises(lambda:build_elevation_candidate(b,(2,1),cross,config(),(0,.1,.11),(0,.8,.81)),'INSUFFICIENT')
def test_uncovered_target_rejected():
    a,b,cross=fixture();raises(lambda:build_elevation_candidate(b,(2,1),cross,config(),(0,.6,.75),(0,.8,.95)),'TARGET_NOT_COVERED')
def test_arc_preserved_without_cutting():
    arc=PlanarArcSegment3D(0,5,0,5,-pi/2,pi/2)
    r=Route3D(3,[line((-20,0,0),(0,0,0)),arc,line((5,5,0),(5,25,0))])
    cs,f=elevation_candidates(r,(3,4),[arc.point_at(.5)],config());assert cs and f is None
    lifted=[p for p in cs[0].route.primitives if isinstance(p,PlanarArcSegment3D)]
    assert len(lifted)==1 and lifted[0].sweep_angle==arc.sweep_angle and lifted[0].radius==arc.radius
    assert lifted[0].z==1 and lifted[0].length()==arc.length()
def test_arc_window_rejected():
    arc=PlanarArcSegment3D(0,5,0,5,-pi/2,pi/2)
    r=Route3D(3,[line((-20,0,0),(0,0,0)),arc,line((5,5,0),(5,25,0))])
    raises(lambda:build_elevation_candidate(r,(3,4),[arc.point_at(.5)],config(),(1,.1,.2),(2,.5,.9)),'NO_VALID_TRANSITION_WINDOW')
def test_boolean_clearance_rejected(): raises(lambda:LayerConfiguration([Layer(0,0),Layer(1,1)],True,5,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC'),'POSITIVE_EXPLICIT')
