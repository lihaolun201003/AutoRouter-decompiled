"""3D foundation contracts; no allocator/collision/layer assignment."""
from copy import deepcopy
from math import pi,sin,cos,sqrt,hypot,fsum,isclose
from src.models import Point3D,Point2D,Layer,Route,SmoothedRoute2D
from src.geometry import smooth_orthogonal_route_2d,build_special_z_smoothed_route_2d,smoothed_route_length
from src.geometry_3d import LineSegment3D,PlanarArcSegment3D,CosineTransition3D,Route3D,lift_smoothed_route_to_layer

def raises(fn,text='',kind=ValueError):
    try:fn()
    except kind as e:assert text in str(e)
    else:raise AssertionError('Expected exception')

def transition(dz=1):return CosineTransition3D(Point3D(0,0,0),Point3D(10,0,dz))

def test_point_distance():assert Point3D(0,0,0).distance_to(Point3D(2,3,6))==7

def test_point_finite():
    for bad in (float('nan'),float('inf'),-float('inf'),True,'1'):
        raises(lambda:Point3D(0,bad,0))

def test_point_equality_tolerance():
    a,b=Point3D(0,0,0),Point3D(1e-10,0,0)
    assert a!=b and a.is_close(b) and not a.is_close(b,0)
    raises(lambda:a.is_close(b,-1))
    raises(lambda:a.is_close(b,float('nan')))

def test_point_mutation_revalidated():
    a=Point3D(0,0,0);a.z=float('nan')
    raises(lambda:a.distance_to(Point3D(1,0,0)))

def test_layer_compatibility_aliases():
    l=Layer(id=17,z=-3.25)
    assert l.id==l.layer_id==17 and l.z==l.z_mm==-3.25
    raises(lambda:Layer(0,float('inf')))
    raises(lambda:Layer(True,0))

def test_line_length_direction():
    l=LineSegment3D(Point3D(0,0,0),Point3D(2,3,6))
    assert l.length()==7 and l.direction()==(2/7,3/7,6/7)

def test_line_interpolation():
    l=LineSegment3D(Point3D(1,2,3),Point3D(3,6,9))
    assert l.point_at(.5)==Point3D(2,4,6) and l.point_at(0)==l.start and l.point_at(1)==l.end

def test_line_degenerate_rejected():raises(lambda:LineSegment3D(Point3D(0,0,0),Point3D(0,0,0)))

def test_invalid_parameters_all_primitives():
    ps=(LineSegment3D(Point3D(0,0,0),Point3D(1,0,0)),transition(),PlanarArcSegment3D(0,0,2,5,0,pi/2))
    for p in ps:
        for t in (-.01,1.01,float('nan'),float('inf'),True):
            raises(lambda:p.point_at(t));raises(lambda:p.tangent_at(t))

def test_cosine_endpoints():
    c=transition();assert c.point_at(0)==Point3D(0,0,0) and c.point_at(1)==Point3D(10,0,1)

def test_cosine_midpoint():assert transition().point_at(.5).is_close(Point3D(5,0,.5),1e-14)

def test_cosine_xy_arbitrary_direction():
    c=CosineTransition3D(Point3D(2,3,8),Point3D(-4,11,6))
    assert c.lxy==10
    p=c.point_at(.25);assert p.x==.5 and p.y==5
    assert isclose(p.z,8-(1-cos(pi*.25)),abs_tol=1e-14)

def test_cosine_up_down_monotonicity():
    for dz in (1,-1):
        points=[transition(dz).point_at(i/100) for i in range(101)]
        assert all((b.z-a.z)*dz>0 for a,b in zip(points,points[1:]))

def test_cosine_endpoint_slopes_exact_zero():
    c=transition()
    assert c.tangent_at(0)==c.tangent_at(1)==(10,0,0.)
    assert isclose(c.tangent_at(.5)[2],pi/2)

def test_cosine_tangent_finite_difference():
    c=transition(-2);t=.37;h=1e-6;a=c.point_at(t-h);b=c.point_at(t+h)
    assert all(abs(d-e)<1e-8 for d,e in zip(c.tangent_at(t),((b.x-a.x)/(2*h),(b.y-a.y)/(2*h),(b.z-a.z)/(2*h))))

def test_cosine_no_height_change():raises(lambda:transition(0),'NOT_A_LAYER_TRANSITION')

def test_cosine_vertical_rejected():raises(lambda:CosineTransition3D(Point3D(0,0,0),Point3D(0,0,1)),'INSUFFICIENT_TRANSITION_RUN')

def test_indicator_fixture():assert transition().effective_radius_indicator()==25.25

def test_indicator_sign_invariance():assert transition(-1).effective_radius_indicator()==transition(1).effective_radius_indicator()

def test_length_exceeds_chord():assert transition().length()>sqrt(101)

def test_length_height_monotonic():
    lengths=[transition(z).length() for z in (.1,1,5,20)]
    assert lengths==sorted(lengths) and len(set(lengths))==4

def test_length_independent_midpoint_quadrature():
    # Composite midpoint, independent of adaptive Simpson recursion/error estimate.
    n=16384
    for dz in (.1,1,10,100):
        expected=fsum(hypot(10,dz*pi/2*sin(pi*(i+.5)/n)) for i in range(n))/n
        assert abs(transition(dz).length()-expected)<2e-9

def test_length_repeat_and_tolerance():
    c=transition();a=c.length();b=c.length()
    assert a==b and abs(a-c.length(1e-12,1e-14))<1e-10

def test_length_sign_and_rotation_invariant():
    a=transition();b=CosineTransition3D(Point3D(0,0,1),Point3D(6,8,0))
    assert abs(a.length()-b.length())<1e-12

def test_length_failure_explicit():
    raises(lambda:transition().length(-1))
    raises(lambda:transition().length(max_depth=True))
    raises(lambda:transition(100).length(1e-15,0,0),'NOT_CONVERGED',RuntimeError)

def test_arc_length_fixed_z():
    a=PlanarArcSegment3D(2,3,7,5,0,pi/2)
    assert a.length()==5*pi/2 and all(a.point_at(t).z==7 for t in (0,.2,.5,1))

def test_arc_endpoints_clockwise():
    a=PlanarArcSegment3D(0,0,7,5,pi/2,-pi/2)
    assert a.start.is_close(Point3D(0,5,7)) and a.end.is_close(Point3D(5,0,7))
    assert a.tangent_at(0)[0]>0 and a.tangent_at(1)[1]<0

def test_arc_invalid():
    for r,s in ((0,1),(-1,1),(5,0),(5,4)):
        raises(lambda:PlanarArcSegment3D(0,0,0,r,0,s))
    raises(lambda:PlanarArcSegment3D(0,0,float('nan'),5,0,1))

def test_route_continuity_and_total():
    a=LineSegment3D(Point3D(-2,0,0),Point3D(0,0,0));c=transition()
    b=LineSegment3D(Point3D(10,0,1),Point3D(12,0,1));r=Route3D(9,[a,c,b])
    assert r.start_point==a.start and r.end_point==b.end
    assert isclose(r.total_length(),4+c.length(),abs_tol=1e-12)
    assert a.direction()==b.direction()==(1.,0.,0.)

def test_route_discontinuity_rejected():raises(lambda:Route3D(1,[transition(),transition()]),'DISCONTINUOUS')

def test_route_empty():
    r=Route3D(1,[]);assert r.total_length()==0 and r.start_point is None and r.end_point is None

def test_route_invalid_primitive():raises(lambda:Route3D(1,[object()]),kind=TypeError)

def test_route_input_isolation():
    a=Point3D(0,0,0);c=transition();r=Route3D(1,[c]);c.start.x=8
    assert r.start_point==a
    p=r.start_point;p.x=10;assert r.start_point==a

def ordinary():return smooth_orthogonal_route_2d(Route(8,[Point2D(0,150),Point2D(0,100),Point2D(20,100),Point2D(20,150)]),5)

def special():return build_special_z_smoothed_route_2d(10,Point2D(0,0),Point2D(3,150),5)

def check_lift(r):
    layer=Layer(55,-2.75);before=deepcopy((r,layer));lifted=lift_smoothed_route_to_layer(r,layer)
    assert before==(r,layer) and len(r.segments)==len(lifted.primitives)
    assert lifted.total_length()==smoothed_route_length(r)
    for a,b in zip(r.segments,lifted.primitives):
        assert (a.start.x,a.start.y)==(b.start.x,b.start.y)
        assert (a.end.x,a.end.y)==(b.end.x,b.end.y)
        assert b.start.z==b.end.z==layer.z
    return lifted

def test_ordinary_lifting():check_lift(ordinary())

def test_special_lifting():
    r=check_lift(special());assert sum(isinstance(p,PlanarArcSegment3D) for p in r.primitives)==2

def test_lift_interior_circle_xy():
    a=ordinary();r=check_lift(a)
    for p in r.primitives:
        if isinstance(p,PlanarArcSegment3D):
            for t in (.1,.5,.9):
                v=p.point_at(t);assert abs(hypot(v.x-p.center_x,v.y-p.center_y)-p.radius)<1e-12

def test_lift_no_shared_geometry():
    a=ordinary();r=check_lift(a);before=deepcopy(a)
    r.primitives[0].start.x=99
    assert a==before

def test_lift_empty():assert lift_smoothed_route_to_layer(SmoothedRoute2D(5,[]),Layer(0,4)).primitives==()

def test_lift_layer_mutation_validation():
    l=Layer(1,3);l.z=float('inf');raises(lambda:lift_smoothed_route_to_layer(ordinary(),l))
