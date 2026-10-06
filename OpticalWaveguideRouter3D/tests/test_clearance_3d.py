"""Small analytic/adversarial fixtures, no routing or production layer choices."""
from copy import deepcopy
from math import pi,sqrt,hypot,isclose
from src.models import Point3D
from src.geometry_3d import LineSegment3D,PlanarArcSegment3D,CosineTransition3D,Route3D
from src.clearance_3d import (line_line_minimum_distance_3d,planar_primitive_minimum_distance,
    fixed_layer_clearance_certificate,analyze_primitive_clearance,adaptive_primitive_minimum_distance,
    analyze_route3d_clearance,analyze_route3d_self_clearance)

def line(a,b):return LineSegment3D(Point3D(*a),Point3D(*b))
def trans():return CosineTransition3D(Point3D(0,0,0),Point3D(10,0,1))
def fixture(z=1):return line((0,0,0),(10,0,0)),line((5,-5,z),(5,5,z))
def approx(a,b,tol=1e-8):assert abs(a-b)<=tol,(a,b)

def test_line_3d_intersection():
    a,b=fixture(0);d=line_line_minimum_distance_3d(a,b)
    assert d.distance_mm==0 and d.parameter_a==d.parameter_b==.5 and d.closest_point_a==d.closest_point_b

def test_line_parallel():
    d=line_line_minimum_distance_3d(line((0,0,0),(10,0,0)),line((1,3,0),(9,3,0)))
    assert d.distance_mm==3

def test_line_skew():
    a,b=fixture();d=line_line_minimum_distance_3d(a,b)
    assert d.distance_mm==1 and d.parameter_a==d.parameter_b==.5

def test_line_endpoint_minimum():
    a=line((0,0,0),(1,0,0));b=line((2,1,1),(2,2,1));d=line_line_minimum_distance_3d(a,b)
    approx(d.distance_mm,sqrt(3));assert d.parameter_a==1 and d.parameter_b==0

def test_line_nearly_parallel_interior():
    a=line((0,0,0),(10,0,0));b=line((0,1e-6,1),(10,-1e-6,1))
    d=line_line_minimum_distance_3d(a,b);approx(d.distance_mm,1);approx(d.parameter_a,.5)

def test_line_reversal_distance():
    a,b=fixture();d=line_line_minimum_distance_3d(line(tuple((a.end.x,a.end.y,a.end.z)),tuple((a.start.x,a.start.y,a.start.z))),b)
    assert d.distance_mm==1

def test_same_layer_intersection_kernel():
    a,b=fixture(0);r=analyze_primitive_clearance(a,b,.5)
    assert r['status']=='COLLISION' and r['minimum_distance_mm']==0 and r['xy_intersection_kinds']==('cross',)

def test_same_layer_touch_overlap():
    a=line((0,0,0),(10,0,0))
    for b,kind in ((line((10,0,0),(11,1,0)),'touch'),(line((2,0,0),(8,0,0)),'overlap')):
        r=analyze_primitive_clearance(a,b,.1);assert r['minimum_distance_mm']==0 and kind in r['xy_intersection_kinds']

def test_layer_clear_certificate():
    a,b=fixture();r=fixed_layer_clearance_certificate(a,b,.5)
    assert r['status']=='CLEAR_BY_LAYER_SEPARATION' and r['distance_lower_bound_mm']==1 and r['minimum_distance_mm'] is None
    assert analyze_primitive_clearance(a,b,.5)['status']=='CLEAR'

def test_layer_insufficient():
    a,b=fixture();r=analyze_primitive_clearance(a,b,1.5)
    assert r['status']=='COLLISION' and r['intersection_status']=='DISJOINT' and r['minimum_distance_mm']==1

def test_layer_threshold():
    a,b=fixture();assert analyze_primitive_clearance(a,b,1.)['status']=='TOUCHING_THRESHOLD'

def test_near_layer_hand_calculation():
    a=line((0,0,0),(10,0,0));b=line((0,.08,.05),(10,.08,.05))
    r=analyze_primitive_clearance(a,b,.1);approx(r['minimum_distance_mm'],sqrt(.05**2+.08**2));assert r['status']=='COLLISION'

def test_fixed_z_not_approximate():
    a,b=fixture();b=line((5,-5,1),(5,5,1+1e-12))
    assert fixed_layer_clearance_certificate(a,b,.5) is None

def test_arc_line_interior_stationary():
    arc=PlanarArcSegment3D(0,0,0,1,0,pi);a=line((-2,2,0),(2,2,0))
    d=planar_primitive_minimum_distance(a,arc)
    approx(d.distance_mm,1);approx(d.parameter_a,.5);approx(d.parameter_b,.5)

def test_arc_line_intersection():
    arc=PlanarArcSegment3D(0,0,0,1,0,pi);a=line((0,0,0),(0,2,0))
    r=analyze_primitive_clearance(a,arc,.1);assert r['minimum_distance_mm']==0 and r['status']=='COLLISION'

def test_arc_line_other_layer():
    arc=PlanarArcSegment3D(0,0,3,1,0,pi);a=line((-2,2,0),(2,2,0))
    approx(planar_primitive_minimum_distance(a,arc).distance_mm,sqrt(10))

def test_arc_arc_interior_stationary():
    a=PlanarArcSegment3D(0,0,0,1,-pi/2,pi);b=PlanarArcSegment3D(4,0,0,1,pi/2,pi)
    d=planar_primitive_minimum_distance(a,b);approx(d.distance_mm,2);approx(d.parameter_a,.5);approx(d.parameter_b,.5)

def test_arc_concentric_overlap_angles():
    a=PlanarArcSegment3D(0,0,0,1,0,pi);b=PlanarArcSegment3D(0,0,.5,2,pi/4,pi/2)
    approx(planar_primitive_minimum_distance(a,b).distance_mm,hypot(1,.5))

def test_arc_arc_cross():
    a=PlanarArcSegment3D(0,0,0,2,0,pi);b=PlanarArcSegment3D(2,0,0,2,0,pi)
    r=analyze_primitive_clearance(a,b,.1);assert r['minimum_distance_mm']==0 and r['status']=='COLLISION'

def test_arc_clockwise_wrapped():
    a=PlanarArcSegment3D(0,0,0,1,pi/4,-pi/2);b=line((2,-2,0),(2,2,0))
    d=planar_primitive_minimum_distance(a,b);approx(d.distance_mm,1);approx(d.parameter_a,.5)

def test_transition_line_interior_cross():
    c=trans();b=line((5,-2,.5),(5,2,.5));r=analyze_primitive_clearance(c,b,.1)
    assert r['status']=='COLLISION' and r['minimum_distance_mm']==0 and r['parameter_a']==.5
    assert r['intersection_status']=='INTERSECTING_WITNESS'

def independent_transition_line_reference(z=.65):
    # Scalar golden-section minimization of analytic fixture squared distance;
    # no chord distances, adaptive cells, or production distance APIs.
    from math import cos,pi
    f=lambda t:(10*t-5)**2+((1-cos(pi*t))/2-z)**2
    lo,hi=0.,1.;g=(sqrt(5)-1)/2
    x=hi-g*(hi-lo);y=lo+g*(hi-lo)
    for _ in range(120):
        if f(x)<f(y):hi=y;y=x;x=hi-g*(hi-lo)
        else:lo=x;x=y;y=lo+g*(hi-lo)
    t=(lo+hi)/2
    return sqrt(f(t)),t

def test_transition_line_nonzero_interior_reference():
    r=analyze_primitive_clearance(trans(),line((5,-2,.65),(5,2,.65)),.1,distance_tol=1e-7)
    d,t=independent_transition_line_reference()
    assert r['converged'] and r['subdivision_count']>0
    assert r['lower_bound_mm']<=d<=r['upper_bound_mm']
    approx(r['minimum_distance_mm'],d,1e-7);approx(r['parameter_a'],t,1e-4)

def test_transition_arc():
    a=PlanarArcSegment3D(5,1,.5,1,-pi/2,pi/2)
    r=analyze_primitive_clearance(trans(),a,.1)
    assert r['status']=='COLLISION' and r['minimum_distance_mm']<1e-8

def test_transition_transition_cross():
    b=CosineTransition3D(Point3D(5,-5,0),Point3D(5,5,1))
    r=analyze_primitive_clearance(trans(),b,.1)
    assert r['status']=='COLLISION' and r['minimum_distance_mm']==0

def test_transition_transition_separated():
    b=CosineTransition3D(Point3D(0,2,0),Point3D(10,2,1))
    r=analyze_primitive_clearance(trans(),b,1.)
    assert r['status']=='CLEAR';approx(r['minimum_distance_mm'],2)

def test_adaptive_midpoint_zero_deviation_not_safe():
    c=trans();a=line((2.5,-1,.1464466094067262),(2.5,1,.1464466094067262))
    # Full transition midpoint lies ON full chord; curve is not the chord.
    r=analyze_primitive_clearance(c,a,.02)
    assert r['status']=='COLLISION' and r['subdivision_count']>0

def test_adaptive_budget_explicit():
    r=analyze_primitive_clearance(trans(),line((5,-2,.65),(5,2,.65)),.1,max_subdivisions=0)
    assert r['status']=='DISTANCE_NOT_CONVERGED' and not r['converged']

def test_adaptive_boundary_ambiguous():
    b=CosineTransition3D(Point3D(0,2,0),Point3D(10,2,1))
    assert analyze_primitive_clearance(trans(),b,2.)['status']=='AMBIGUOUS_CLEARANCE'

def test_route_pair_minimum_identity():
    a=Route3D(1,[line((0,0,0),(2,0,0)),line((2,0,0),(2,2,0))]);b=Route3D(2,[line((1.5,1,0),(2.5,1,0))])
    r=analyze_route3d_clearance(a,b,.1)
    assert r['status']=='COLLISION' and r['primitive_a_index']==1 and r['primitive_b_index']==0
    assert r['minimum_primitive_identity_certified']

def test_route_uncertainty_propagation():
    a=Route3D(1,[trans()]);b=Route3D(2,[line((5,-2,.65),(5,2,.65))])
    assert analyze_route3d_clearance(a,b,.1,max_subdivisions=0)['status']=='DISTANCE_NOT_CONVERGED'

def test_self_adjacent_join_exclusion():
    r=Route3D(1,[line((-2,0,0),(0,0,0)),trans(),line((10,0,1),(12,0,1))])
    report=analyze_route3d_self_clearance(r,.1)
    assert report['status']=='CLEAR' and len(report['adjacent_results'])==2
    assert all(x['status']=='ADJACENT_JOIN_EXEMPT' for x in report['adjacent_results'])

def test_self_nonadjacent_cross():
    r=Route3D(1,[line((0,0,0),(2,0,0)),line((2,0,0),(2,2,0)),line((2,2,0),(1,-1,0))])
    result=analyze_route3d_self_clearance(r,.1)
    assert result['status']=='COLLISION' and result['primitive_a_index']==0 and result['primitive_b_index']==2

def test_self_adjacent_overlap_not_skipped():
    r=Route3D(1,[line((0,0,0),(2,0,0)),line((2,0,0),(1,0,0))])
    result=analyze_route3d_self_clearance(r,.1)
    assert result['status']=='COLLISION' and result['adjacent_results'][0]['extra_event_kinds']==['overlap']

def test_self_uncertified_transition_adjacency():
    a=trans();b=CosineTransition3D(Point3D(10,0,1),Point3D(0,0,0))
    r=analyze_route3d_self_clearance(Route3D(1,[a,b]),.1)
    assert r['status']=='AMBIGUOUS_CLEARANCE'

def test_read_only():
    a=Route3D(1,[trans()]);b=Route3D(2,[line((5,-2,.65),(5,2,.65))]);before=deepcopy((a,b))
    analyze_route3d_clearance(a,b,.1);analyze_route3d_self_clearance(a,.1)
    assert (a,b)==before

def test_invalid_geometry():assert analyze_primitive_clearance(object(),trans(),.1)['status']=='INVALID_GEOMETRY'

def test_clearance_must_be_explicit():
    try:analyze_primitive_clearance(trans(),trans())
    except TypeError:pass
    else:assert False

def test_invalid_settings():
    for kwargs in ({'clearance_mm':-1},{'clearance_mm':float('nan')},{'clearance_mm':.1,'distance_tol':1e-12}):
        try:analyze_primitive_clearance(trans(),trans(),**kwargs)
        except ValueError:pass
        else:assert False

def test_distance_swap_symmetry():
    a=PlanarArcSegment3D(0,0,.2,1,0,pi);b=line((-2,2,0),(2,2,0))
    x=planar_primitive_minimum_distance(a,b);y=planar_primitive_minimum_distance(b,a)
    assert x.distance_mm==y.distance_mm and x.parameter_a==y.parameter_b and x.parameter_b==y.parameter_a

def test_lifted_2d_cross():
    from src.models import LineSegment2D,SmoothedRoute2D,Point2D,Layer
    from src.geometry_3d import lift_smoothed_route_to_layer
    a=SmoothedRoute2D(1,[LineSegment2D(Point2D(0,0),Point2D(10,0))])
    b=SmoothedRoute2D(2,[LineSegment2D(Point2D(5,-1),Point2D(5,1))])
    r=analyze_route3d_clearance(lift_smoothed_route_to_layer(a,Layer(5,3)),lift_smoothed_route_to_layer(b,Layer(5,3)),.1)
    assert r['minimum_distance_mm']==0 and r['status']=='COLLISION'

def test_lifted_2d_non_cross():
    from src.models import LineSegment2D,SmoothedRoute2D,Point2D,Layer
    from src.geometry_3d import lift_smoothed_route_to_layer
    a=SmoothedRoute2D(1,[LineSegment2D(Point2D(0,0),Point2D(10,0))])
    b=SmoothedRoute2D(2,[LineSegment2D(Point2D(0,1),Point2D(10,1))])
    r=analyze_route3d_clearance(lift_smoothed_route_to_layer(a,Layer(5,3)),lift_smoothed_route_to_layer(b,Layer(5,3)),.1)
    assert r['minimum_distance_mm']==1 and r['status']=='CLEAR'

def test_adjacent_extra_arc_contact_not_skipped():
    a=PlanarArcSegment3D(0,0,0,1,pi,-pi)
    b=line((1,0,0),(-2,0,0))
    r=analyze_route3d_self_clearance(Route3D(1,[a,b]),.1)
    assert r['status']=='COLLISION'

def test_planar_minimum_independent_mesh_bounds():
    # A mesh yields an independent upper bound; speed/(2n) bounds unsampled gaps.
    cases=[
        (PlanarArcSegment3D(0,0,0,1,2.8,-2.4),PlanarArcSegment3D(3,2,.1,1.5,-1.5,2.1)),
        (PlanarArcSegment3D(0,0,0,2,-2.9,1.2),line((1,1,.3),(3,4,.3))),
        (PlanarArcSegment3D(0,0,0,1,.3,1.1),PlanarArcSegment3D(0,0,.1,2,2.5,-1.4))]
    n=80
    for a,b in cases:
        pa=[a.point_at(i/n) for i in range(n+1)];pb=[b.point_at(i/n) for i in range(n+1)]
        sampled=min(x.distance_to(y) for x in pa for y in pb)
        d=planar_primitive_minimum_distance(a,b)
        assert d.distance_mm<=sampled+1e-8
        assert sampled-d.distance_mm<=(a.length()+b.length())/(2*n)+1e-8

def test_clearance_inequalities_hold():
    for c in (.1,.148,.2):
        r=analyze_primitive_clearance(trans(),line((5,-2,.65),(5,2,.65)),c)
        if r['status']=='CLEAR':assert r['minimum_distance_mm']-r['error_bound_mm']>=c
        if r['status']=='COLLISION':assert r['minimum_distance_mm']+r['error_bound_mm']<c
