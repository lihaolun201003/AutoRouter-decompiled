"""Explicit read-only directional joins and cosine inverse-run mathematics.

The C1_DIRECTION name means unit-tangent/G1 continuity, not equality of
parameter derivatives, curvature continuity, loss or manufacturability.
"""
from dataclasses import dataclass
from math import atan2,fsum,hypot,pi,sqrt
from .geometry_3d import (LineSegment3D,PlanarArcSegment3D,CosineTransition3D,
    PathWindowTransition3D,Route3D,_finite)


def minimum_xy_run_for_radius(delta_z,required_radius):
    """pi*sqrt(required_radius*abs(delta_z)/2), in mm. No default radius.

    A zero height change is not a layer transition, consistent with 9-A.
    This is mathematics only; it neither selects nor edits any geometry.
    """
    _finite(delta_z,required_radius)
    if delta_z==0:
        raise ValueError('NOT_A_LAYER_TRANSITION')
    if required_radius<=0:
        raise ValueError('Required radius must be positive.')
    value=(sqrt(required_radius)*sqrt(abs(delta_z)))*(pi/sqrt(2))
    _finite(value)
    if value<=0:
        raise ValueError('TRANSITION_RUN_NOT_REPRESENTABLE')
    return value


@dataclass(frozen=True)
class JoinValidation3D:
    position_continuous: bool
    tangent_continuous: bool
    dot_product: float | None
    angle_rad: float | None
    status: str
    position_gap_mm: float | None = None
    direction_status: str = 'NOT_EVALUATED'
    detail: str | None = None


def _tolerances(position_tol,angle_tol):
    _finite(position_tol,angle_tol)
    if position_tol<0 or not 0<=angle_tol<pi/2:
        raise ValueError('Require position_tol >= 0 and 0 <= angle_tol < pi/2.')


def validate_tangent_join_3d(a,b,*,position_tol=1e-9,angle_tol=1e-9):
    """Normalize a.tangent_at(1), b.tangent_at(0); require same direction.

    Absolute position tolerance is mm; angular tolerance is radians. atan2
    of cross magnitude and dot avoids acos losing small angles. Invalid
    tolerances raise, while invalid geometry is an explicit diagnostic.
    """
    _tolerances(position_tol,angle_tol)
    types=(LineSegment3D,PlanarArcSegment3D,CosineTransition3D,PathWindowTransition3D)
    gap=None
    try:
        if not isinstance(a,types) or not isinstance(b,types):
            raise TypeError('Unsupported primitive type.')
        a.validate();b.validate()
        gap=a.end.distance_to(b.start)
    except (ValueError,TypeError,AttributeError,OverflowError) as ex:
        return JoinValidation3D(False,False,None,None,'INVALID_PRIMITIVE',detail=str(ex))
    if gap>position_tol:
        return JoinValidation3D(False,False,None,None,'POSITION_DISCONTINUOUS',gap)
    try:
        ta=tuple(a.tangent_at(1));tb=tuple(b.tangent_at(0))
        if len(ta)!=3 or len(tb)!=3:
            raise ValueError('Tangent requires three components.')
        _finite(*ta,*tb)
        na,nb=hypot(*ta),hypot(*tb)
        _finite(na,nb)
        if na==0 or nb==0:
            return JoinValidation3D(True,False,None,None,'ZERO_TANGENT',gap)
        u=tuple(x/na for x in ta);v=tuple(x/nb for x in tb)
        dot=max(-1.,min(1.,fsum(x*y for x,y in zip(u,v))))
        cross=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
        angle=atan2(hypot(*cross),dot)
    except (ValueError,TypeError,AttributeError,OverflowError) as ex:
        return JoinValidation3D(True,False,None,None,'INVALID_PRIMITIVE',gap,detail=str(ex))
    passed=angle<=angle_tol
    return JoinValidation3D(True,passed,dot,angle,
        'C0_C1_PASS' if passed else 'TANGENT_DIRECTION_MISMATCH',gap,
        'C1_DIRECTION_CONTINUOUS' if passed else 'TANGENT_DIRECTION_MISMATCH')


@dataclass(frozen=True)
class RouteJoinAnalysis3D:
    route_id: int
    joins: tuple[JoinValidation3D,...]
    all_C0: bool
    all_C1_direction: bool


def analyze_route3d_joins(route,*,position_tol=None,angle_tol=1e-9):
    """Read each consecutive join; index i means primitives i -> i+1.

    Uses route.continuity_tol unless explicitly overridden. Does not call
    route.validate(): mutated/disconnected joins must be reported, not hidden
    by an early constructor-style exception. Empty join sets pass vacuously;
    this is not a whole-route primitive validity certificate.
    """
    if not isinstance(route,Route3D):
        raise TypeError('Expected Route3D.')
    tol=route.continuity_tol if position_tol is None else position_tol
    _tolerances(tol,angle_tol)
    joins=tuple(validate_tangent_join_3d(a,b,position_tol=tol,angle_tol=angle_tol)
                for a,b in zip(route.primitives,route.primitives[1:]))
    return RouteJoinAnalysis3D(route.route_id,joins,all(j.position_continuous for j in joins),
                               all(j.tangent_continuous for j in joins))
