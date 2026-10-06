"""Analytic curvature checked against point-only finite differences."""
from copy import deepcopy
from math import pi,inf,isclose,hypot,fsum,cos,sin
from src.models import Point3D
from src.geometry_3d import CosineTransition3D,LineSegment3D,PlanarArcSegment3D,Route3D
from src.geometry_3d_diagnostics import minimum_xy_run_for_radius,validate_tangent_join_3d,analyze_route3d_joins


def expect_error(fn,kind=ValueError):
    try:fn()
    except kind:pass
    else:raise AssertionError('Expected controlled error')


def curve(dz=1):return CosineTransition3D(Point3D(0,0,0),Point3D(10,0,dz))


def incoming(start):return LineSegment3D(Point3D(*start),Point3D(0,0,0))


def good_arc():return PlanarArcSegment3D(0,1,0,1,-pi,pi/2)


def bad_arc():return PlanarArcSegment3D(-1,0,0,1,-pi/2,pi/2)


def numeric_curvature(c,t,h=1e-3):
    """Point-only five-point stencils; no analytic derivatives or curvature API.

    Endpoint stencils stay within [0,1]. Interior uses centered stencils.
    Reversing the parameter at the right endpoint leaves curvature unchanged.
    """
    if t==0 or t==1:
        ts=[t+(1 if t==0 else -1)*i*h for i in range(5)]
        w1=(-25,48,-36,16,-3);w2=(35,-104,114,-56,11)
    else:
        ts=[t+i*h for i in (-2,-1,0,1,2)]
        w1=(1,-8,0,8,-1);w2=(-1,16,-30,16,-1)
    ps=[c.point_at(x) for x in ts]
    coords=[(p.x,p.y,p.z) for p in ps]
    d1=tuple(fsum(w*p[j] for w,p in zip(w1,coords))/(12*h) for j in range(3))
    d2=tuple(fsum(w*p[j] for w,p in zip(w2,coords))/(12*h*h) for j in range(3))
    cross=(d1[1]*d2[2]-d1[2]*d2[1],d1[2]*d2[0]-d1[0]*d2[2],d1[0]*d2[1]-d1[1]*d2[0])
    return hypot(*cross)/hypot(*d1)**3


def test_curvature_endpoints():
    c=curve();expected=pi*pi/200
    assert isclose(c.curvature_at(0),expected,rel_tol=1e-14)
    assert c.curvature_at(1)==c.curvature_at(0)==c.max_curvature()

def test_curvature_midpoint_zero():assert curve().curvature_at(.5)==0

def test_zero_curvature_radius_infinity():assert curve().radius_of_curvature_at(.5)==inf

def test_curvature_symmetry():
    c=curve()
    for t in (0,.01,.1,.25,.49):assert isclose(c.curvature_at(t),c.curvature_at(1-t),rel_tol=1e-13)

def test_curvature_height_sign():
    for t in (0,.1,.25,.5,.9,1):assert curve(1).curvature_at(t)==curve(-1).curvature_at(t)

def test_curvature_xy_rotation():
    c=CosineTransition3D(Point3D(4,7,2),Point3D(10,15,3))
    for t in (0,.1,.25,.5,.75,1):assert c.curvature_at(t)==curve().curvature_at(t)

def test_true_radius_hand_calculation():assert isclose(curve().minimum_curvature_radius(),200/pi**2,rel_tol=1e-14)

def test_reff_retained_distinct():
    c=curve();assert c.effective_radius_indicator()==25.25 and c.effective_radius_indicator()!=c.minimum_curvature_radius()

def test_local_radius_reciprocal():
    for t in (0,.1,.25,.75,.9,1):assert isclose(curve().radius_of_curvature_at(t)*curve().curvature_at(t),1,rel_tol=1e-14)

def test_max_curvature_sample_regression():
    for dz in (.01,1,10):
        c=curve(dz);assert all(c.curvature_at(i/100)<=c.max_curvature() for i in range(101))

def test_numeric_versus_analytic():
    cs=[curve(),curve(-1),CosineTransition3D(Point3D(4,7,2),Point3D(10,15,3))]
    for c in cs:
        for t in (0,.1,.25,.5,.75,.9,1):
            assert abs(numeric_curvature(c,t)-c.curvature_at(t))<2e-7

def test_curvature_invalid_parameter():
    for t in (-1,2,float('nan'),float('inf'),True):
        expect_error(lambda:curve().curvature_at(t))
        expect_error(lambda:curve().radius_of_curvature_at(t))

def test_curvature_invalid_mutation():
    c=curve();c.end.z=0
    expect_error(c.max_curvature);expect_error(c.minimum_curvature_radius)

def test_inverse_radius_fixture():
    assert isclose(minimum_xy_run_for_radius(1,200/pi**2),10,rel_tol=1e-14)

def test_inverse_satisfies_requested_radius():
    for dz in (.1,1,-2):
        for radius in (1,7,23):
            run=minimum_xy_run_for_radius(dz,radius)
            c=CosineTransition3D(Point3D(0,0,0),Point3D(run,0,dz))
            assert isclose(c.minimum_curvature_radius(),radius,rel_tol=1e-14)
            longer=CosineTransition3D(Point3D(0,0,0),Point3D(run*1.1,0,dz))
            assert longer.minimum_curvature_radius()>radius

def test_inverse_no_default_and_invalid():
    expect_error(lambda:minimum_xy_run_for_radius(1),TypeError)
    for dz,r in ((0,1),(1,0),(1,-1),(float('nan'),1),(1,float('inf')),(True,1)):
        expect_error(lambda:minimum_xy_run_for_radius(dz,r))

def test_line_transition_pass():
    result=validate_tangent_join_3d(incoming((-2,0,0)),curve())
    assert result.position_continuous and result.tangent_continuous and result.status=='C0_C1_PASS'
    assert result.dot_product==1 and result.angle_rad==0 and result.direction_status=='C1_DIRECTION_CONTINUOUS'

def test_perpendicular_line_fail():
    r=validate_tangent_join_3d(incoming((0,-2,0)),curve())
    assert r.position_continuous and not r.tangent_continuous and r.status=='TANGENT_DIRECTION_MISMATCH'
    assert r.dot_product==0 and r.angle_rad==pi/2

def test_reverse_tangent_fail():
    r=validate_tangent_join_3d(incoming((2,0,0)),curve())
    assert r.status=='TANGENT_DIRECTION_MISMATCH' and r.dot_product==-1 and r.angle_rad==pi

def test_arc_transition_pass():assert validate_tangent_join_3d(good_arc(),curve()).status=='C0_C1_PASS'

def test_arc_c0_pass_c1_fail():
    route=Route3D(1,[bad_arc(),curve()]);r=analyze_route3d_joins(route)
    assert r.all_C0 and not r.all_C1_direction and r.joins[0].status=='TANGENT_DIRECTION_MISMATCH'

def test_position_discontinuity():
    r=validate_tangent_join_3d(curve(),curve())
    assert r.status=='POSITION_DISCONTINUOUS' and not r.position_continuous and r.dot_product is None

def test_zero_tangent_diagnostic():
    # Valid geometric line with a deliberately damaged tangent provider.
    class ZeroTangent(LineSegment3D):
        def tangent_at(self,t):return (0.,0.,0.)
    a=ZeroTangent(Point3D(-1,0,0),Point3D(0,0,0))
    r=validate_tangent_join_3d(a,curve())
    assert r.status=='ZERO_TANGENT' and r.position_continuous and r.angle_rad is None

def test_invalid_primitive_diagnostic():
    assert validate_tangent_join_3d(object(),curve()).status=='INVALID_PRIMITIVE'
    a=incoming((-1,0,0));a.start.z=float('nan')
    assert validate_tangent_join_3d(a,curve()).status=='INVALID_PRIMITIVE'

def test_nonfinite_tangent_diagnostic():
    class BadTangent(LineSegment3D):
        def tangent_at(self,t):return (float('nan'),0.,0.)
    a=BadTangent(Point3D(-1,0,0),Point3D(0,0,0))
    assert validate_tangent_join_3d(a,curve()).status=='INVALID_PRIMITIVE'

def test_join_invalid_tolerances():
    for kwargs in ({'position_tol':-1},{'angle_tol':-1},{'angle_tol':pi},{'angle_tol':float('nan')}):
        expect_error(lambda:validate_tangent_join_3d(good_arc(),curve(),**kwargs))

def test_small_angle_threshold():
    theta=1e-6;a=incoming((-cos(theta),-sin(theta),0))
    assert validate_tangent_join_3d(a,curve(),angle_tol=theta/2).status=='TANGENT_DIRECTION_MISMATCH'
    assert validate_tangent_join_3d(a,curve(),angle_tol=theta*2).status=='C0_C1_PASS'

def test_route_all_joins():
    tail=LineSegment3D(Point3D(10,0,1),Point3D(14,0,1))
    r=Route3D(3,[incoming((-2,0,0)),curve(),tail]);a=analyze_route3d_joins(r)
    assert len(a.joins)==2 and a.all_C0 and a.all_C1_direction

def test_route_read_only_and_geometry_unchanged():
    r=Route3D(3,[good_arc(),curve()]);before=deepcopy(r)
    a=analyze_route3d_joins(r);c=r.primitives[1]
    for t in (0,.1,.25,.5,.75,1):c.curvature_at(t);c.radius_of_curvature_at(t)
    assert a.all_C1_direction and r==before

def test_empty_single_route_join_convention():
    for r in (Route3D(1,[]),Route3D(2,[curve()])):
        a=analyze_route3d_joins(r);assert not a.joins and a.all_C0 and a.all_C1_direction

def test_mutated_route_discontinuity_is_reported():
    r=Route3D(1,[incoming((-2,0,0)),curve()]);r.primitives[0].end.x=1
    result=analyze_route3d_joins(r)
    assert not result.all_C0 and result.joins[0].status=='POSITION_DISCONTINUOUS'

def test_g1_not_parameter_c1():
    a=incoming((-2,0,0));b=curve()
    assert a.tangent_at(1)!=b.tangent_at(0) and validate_tangent_join_3d(a,b).tangent_continuous

def test_transition_endpoint_direction():
    c=CosineTransition3D(Point3D(0,0,2),Point3D(6,8,-1))
    assert c.tangent_at(0)==c.tangent_at(1)==(6,8,0)

def test_inverse_sign_invariance():assert minimum_xy_run_for_radius(2,7)==minimum_xy_run_for_radius(-2,7)
