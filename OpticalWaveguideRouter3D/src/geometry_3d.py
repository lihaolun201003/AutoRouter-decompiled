"""Analytic 3D foundation in mm. No routing, collision or layer-spacing policy.

tangent_at returns d(position)/dt, NOT a unit vector. Cosine effective radius
is a project-specific indicator, not minimum curvature radius.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from math import atan2, cos, sin, pi, hypot, fsum, isfinite, sqrt
from .models import Point3D, Layer, LineSegment2D, ArcSegment2D, SmoothedRoute2D
from .geometry import validate_smoothed_route_2d, arc_segment_radius


def _finite(*values):
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) for v in values):
        raise ValueError('Expected finite numeric geometry values.')


def _parameter(t):
    _finite(t)
    if not 0 <= t <= 1:
        raise ValueError('Parameter t must be in [0,1].')


def _copy_point(p):
    if not isinstance(p,Point3D):
        raise TypeError('Expected Point3D.')
    p.validate()
    return Point3D(p.x,p.y,p.z)


@dataclass(frozen=True)
class LineSegment3D:
    start: Point3D
    end: Point3D

    def __post_init__(self):
        object.__setattr__(self,'start',_copy_point(self.start))
        object.__setattr__(self,'end',_copy_point(self.end))
        self.validate()

    def validate(self):
        if self.start.distance_to(self.end) == 0:
            raise ValueError('ZERO_LENGTH_LINE')

    def length(self):
        self.validate()
        return self.start.distance_to(self.end)

    def direction(self):
        length=self.length()
        return tuple(v/length for v in self.tangent_at(0))

    def tangent_at(self,t):
        _parameter(t);self.validate()
        return self.end.x-self.start.x,self.end.y-self.start.y,self.end.z-self.start.z

    def point_at(self,t):
        _parameter(t);self.validate()
        if t==0:return _copy_point(self.start)
        if t==1:return _copy_point(self.end)
        return Point3D(*((1-t)*a+t*b for a,b in zip(
            (self.start.x,self.start.y,self.start.z),(self.end.x,self.end.y,self.end.z))))


@dataclass(frozen=True)
class PlanarArcSegment3D:
    """Fixed-z circle, signed radians; same <= pi sweep domain as 2D arcs.

Lifted arcs additionally retain original endpoint XY values to avoid a
trigonometric round-trip changing their stored endpoints. The circular locus
is still analytic, not a polyline; 2D validation controls rounding tolerance.
"""
    center_x: float
    center_y: float
    z: float
    radius: float
    start_angle: float
    sweep_angle: float
    _source_start_xy: tuple | None = field(default=None,init=False,repr=False)
    _source_end_xy: tuple | None = field(default=None,init=False,repr=False)

    def __post_init__(self):
        self.validate()

    def validate(self):
        _finite(self.center_x,self.center_y,self.z,self.radius,self.start_angle,self.sweep_angle)
        if self.radius<=0 or not 0<abs(self.sweep_angle)<=pi:
            raise ValueError('Invalid planar arc radius/sweep.')
        _finite(self.radius*abs(self.sweep_angle),self.start_angle+self.sweep_angle)

    def point_at(self,t):
        _parameter(t);self.validate()
        original=self._source_start_xy if t==0 else self._source_end_xy if t==1 else None
        if original is not None:return Point3D(*original,self.z)
        a=self.start_angle+t*self.sweep_angle
        return Point3D(self.center_x+self.radius*cos(a),self.center_y+self.radius*sin(a),self.z)

    def tangent_at(self,t):
        _parameter(t);self.validate()
        a=self.start_angle+t*self.sweep_angle
        scale=self.radius*self.sweep_angle
        return -scale*sin(a),scale*cos(a),0.

    def length(self):
        self.validate()
        return self.radius*abs(self.sweep_angle)

    @property
    def start(self):return self.point_at(0)

    @property
    def end(self):return self.point_at(1)


@dataclass(frozen=True)
class CosineTransition3D:
    start: Point3D
    end: Point3D

    def __post_init__(self):
        object.__setattr__(self,'start',_copy_point(self.start))
        object.__setattr__(self,'end',_copy_point(self.end))
        self.validate()

    def validate(self):
        self.start.validate();self.end.validate()
        dx,dy,dz=self.end.x-self.start.x,self.end.y-self.start.y,self.end.z-self.start.z
        _finite(dx,dy,dz,hypot(dx,dy),dz*(pi/2))
        if dz==0:raise ValueError('NOT_A_LAYER_TRANSITION')
        if hypot(dx,dy)<=0:raise ValueError('INSUFFICIENT_TRANSITION_RUN')

    @property
    def lxy(self):
        self.validate()
        return hypot(self.end.x-self.start.x,self.end.y-self.start.y)

    @property
    def delta_z(self):
        self.validate()
        return self.end.z-self.start.z

    def point_at(self,t):
        _parameter(t);self.validate()
        if t==0:return _copy_point(self.start)
        if t==1:return _copy_point(self.end)
        # sin^2 avoids cancellation in 1-cos(pi*t) near the starting layer.
        fraction=.5 if t==.5 else sin(pi*t/2)**2
        return Point3D((1-t)*self.start.x+t*self.end.x,
                       (1-t)*self.start.y+t*self.end.y,
                       (1-fraction)*self.start.z+fraction*self.end.z)

    def tangent_at(self,t):
        _parameter(t);self.validate()
        dzdt=0. if t in (0,1) else (self.end.z-self.start.z)*(pi/2)*sin(pi*t)
        return self.end.x-self.start.x,self.end.y-self.start.y,dzdt

    def effective_radius_indicator(self):
        """PROJECT-SPECIFIC Reff_3d, not a curvature bound or acceptance rule."""
        run=self.lxy;dz=abs(self.delta_z)
        result=(run/dz)*(run/4)+dz/4
        _finite(result)
        return result

    def curvature_at(self,t):
        """True curvature (1/mm) of THIS cosine model, not the Reff indicator.

        With s=Lxy*t: z_s=(pi*dz/(2Lxy))*sin(pi*t),
        z_ss=(pi**2*dz/(2Lxy**2))*cos(pi*t),
        kappa=abs(z_ss)/(1+z_s**2)**1.5.
        Project-specific analytic derivation; no manufacturing threshold.
        """
        _parameter(t);self.validate()
        if t==.5:
            return 0.
        # Reflect about the exact inflection to preserve numeric symmetry.
        u=min(t,1-t)
        slope=(abs(self.delta_z)/self.lxy)*(pi/2)*sin(pi*u)
        _finite(slope)
        denominator=hypot(1.,slope)
        value=self.max_curvature()*abs(cos(pi*u))
        value=value/denominator/denominator/denominator
        _finite(value)
        if value<=0:
            raise ValueError('CURVATURE_NOT_REPRESENTABLE')
        return value

    def radius_of_curvature_at(self,t):
        """mm; exact zero curvature at t=.5 yields math.inf, never a sentinel."""
        curvature=self.curvature_at(t)
        if curvature==0:
            return float('inf')
        value=1/curvature
        _finite(value)
        return value

    def max_curvature(self):
        """pi²|dz|/(2Lxy²), attained at BOTH endpoints analytically."""
        self.validate()
        value=((abs(self.delta_z)/self.lxy)/self.lxy)*(pi*pi/2)
        _finite(value)
        if value<=0:
            raise ValueError('CURVATURE_NOT_REPRESENTABLE')
        return value

    def minimum_curvature_radius(self):
        """True R_min in mm, 2Lxy²/(pi²|dz|), not effective_radius_indicator."""
        value=1/self.max_curvature()
        _finite(value)
        return value

    def length(self,abs_tol=1e-10,rel_tol=1e-12,max_depth=20):
        """Adaptive Simpson arc-length integral, deterministic error estimate.

Tolerance is in mm, relative tolerance dimensionless. Nonconvergence raises
instead of returning an unchecked estimate. No simple closed form claimed.
"""
        self.validate();_finite(abs_tol,rel_tol)
        if abs_tol<=0 or rel_tol<0 or type(max_depth) is not int or not 0<=max_depth<=30:
            raise ValueError('Invalid integration tolerance/depth.')
        run=self.lxy;amplitude=abs(self.delta_z)*(pi/2)
        def speed(t):return hypot(run,amplitude*sin(pi*t))
        a,b=0.,1.;fa,fb,fm=speed(a),speed(b),speed(.5)
        whole=(fa+4*fm+fb)/6
        budget=abs_tol+rel_tol*whole
        _finite(whole,budget)
        def refine(a,b,fa,fm,fb,whole,budget,depth):
            m=(a+b)/2;fl=speed((a+m)/2);fr=speed((m+b)/2)
            left=(m-a)*(fa+4*fl+fm)/6;right=(b-m)*(fm+4*fr+fb)/6
            difference=left+right-whole
            if abs(difference)<=15*budget:return left+right+difference/15
            if depth==0:raise RuntimeError('TRANSITION_LENGTH_NOT_CONVERGED')
            return fsum((refine(a,m,fa,fl,fm,left,budget/2,depth-1),
                         refine(m,b,fm,fr,fb,right,budget/2,depth-1)))
        value=refine(a,b,fa,fm,fb,whole,budget,max_depth)
        _finite(value)
        return value


def planar_sub_curve(p,s,t,z):
    """Exact sub-curve of a fixed-z Line/Arc from parameter s to t (s<t) at height z.

    XY is the ORIGINAL analytic locus, never a chord: an arc stays on its own
    circle with the same sweep sign, a line stays on its own segment. When a
    sub-curve endpoint coincides with the source endpoint (s==0 or t==1 of the
    source arc) the source's stored endpoint XY is carried over so that no
    trigonometric round-trip can move a frozen endpoint.
    """
    _finite(s,t,z)
    if not 0<=s<t<=1:
        raise ValueError('SUBCURVE_PARAMETERS_MUST_BE_AN_INCREASING_INTERVAL')
    if type(p) is LineSegment3D:
        a=p.point_at(s);b=p.point_at(t)
        return LineSegment3D(Point3D(a.x,a.y,z),Point3D(b.x,b.y,z))
    if type(p) is PlanarArcSegment3D:
        arc=PlanarArcSegment3D(p.center_x,p.center_y,z,p.radius,
            p.start_angle+s*p.sweep_angle,(t-s)*p.sweep_angle)
        if s==0 and p._source_start_xy is not None:
            object.__setattr__(arc,'_source_start_xy',tuple(p._source_start_xy))
        if t==1 and p._source_end_xy is not None:
            object.__setattr__(arc,'_source_end_xy',tuple(p._source_end_xy))
        return arc
    raise TypeError('SUBCURVE_REQUIRES_A_FIXED_Z_LINE_OR_ARC')

@dataclass(frozen=True)
class PathWindowTransition3D:
    """One LOGICAL rise/fall that follows the frozen planar path exactly.

    The window covers a contiguous planar ARC-LENGTH interval of the frozen 2D
    route and may cross primitive boundaries and cut arcs. pieces is the
    ordered tuple of exact planar sub-curves it covers, each at z=0. The
    vertical profile is ONE shared cosine phase over the whole window:

        u = (s - s0)/(s1 - s0) in [0,1]
        z(u) = z_start + (z_end - z_start)*sin^2(pi*u/2)

    Curvature, with s the planar arc length and kappa_xy the signed planar
    curvature of the current piece (0 on a line, +-1/R on an arc):

        kappa_3D = sqrt(kappa_xy^2*(1+z_s^2) + z_ss^2) / (1+z_s^2)^(3/2)

    Inside one piece kappa_xy is constant, 1+z_s^2 increases and |z_ss|
    decreases on [0,1/2], and the profile is symmetric about u=1/2, so the
    maximum over a piece is attained at one of its ends: max_curvature() is an
    EXACT maximum over the whole window, evaluated at the finitely many piece
    boundaries, never a sampled minimum-radius estimate.
    """
    pieces: tuple
    z_start: float
    z_end: float
    _run: float = field(default=0.,init=False,repr=False,compare=False)
    _offsets: tuple = field(default=(),init=False,repr=False,compare=False)

    def __post_init__(self):
        pieces=tuple(self.pieces)
        if not pieces:
            raise ValueError('PATH_WINDOW_REQUIRES_AT_LEAST_ONE_PIECE')
        offsets=[];run=0.
        for p in pieces:
            if type(p) not in (LineSegment3D,PlanarArcSegment3D):
                raise TypeError('PATH_WINDOW_PIECES_MUST_BE_FIXED_Z_LINES_OR_ARCS')
            p.validate()
            if p.start.z!=0. or p.end.z!=0.:
                raise ValueError('PATH_WINDOW_PIECES_MUST_SIT_ON_LAYER_ZERO')
            offsets.append(run);run+=p.length()
        for a,b in zip(pieces,pieces[1:]):
            if not a.end.is_close(b.start,1e-9):
                raise ValueError('PATH_WINDOW_PIECES_ARE_NOT_CONTINUOUS')
        _finite(self.z_start,self.z_end,run)
        if run<=0:
            raise ValueError('PATH_WINDOW_HAS_NO_PLANAR_RUN')
        if self.z_end==self.z_start:
            raise ValueError('NOT_A_LAYER_TRANSITION')
        object.__setattr__(self,'pieces',pieces)
        object.__setattr__(self,'_run',run)
        object.__setattr__(self,'_offsets',tuple(offsets))
        self.validate()

    def validate(self):
        if not self.pieces:
            raise ValueError('PATH_WINDOW_REQUIRES_AT_LEAST_ONE_PIECE')
        for p in self.pieces:
            if type(p) not in (LineSegment3D,PlanarArcSegment3D):
                raise TypeError('PATH_WINDOW_PIECES_MUST_BE_FIXED_Z_LINES_OR_ARCS')
            p.validate()
        _finite(self.z_start,self.z_end,self._run)
        if self.z_end==self.z_start:
            raise ValueError('NOT_A_LAYER_TRANSITION')
        return True

    @property
    def planar_run_mm(self):
        self.validate()
        return self._run

    @property
    def delta_z(self):
        self.validate()
        return self.z_end-self.z_start

    @property
    def is_rise(self):
        self.validate()
        return self.z_end>self.z_start

    @property
    def piece_offsets(self):
        self.validate()
        return self._offsets

    def piece_curvature(self,k):
        """Signed planar curvature of piece k (1/mm); exactly 0 for a line."""
        p=self.pieces[k]
        if type(p) is PlanarArcSegment3D:
            return (1. if p.sweep_angle>0 else -1.)/p.radius
        return 0.

    def max_planar_curvature(self):
        self.validate()
        return max((abs(self.piece_curvature(k)) for k in range(len(self.pieces))),default=0.)
    def _locate(self,u):
        """(piece index, local parameter) for a window parameter u in [0,1]."""
        _parameter(u)
        if u<=0.:
            return 0,0.
        if u>=1.:
            return len(self.pieces)-1,1.
        s=u*self._run
        for k,offset in enumerate(self._offsets):
            length=self.pieces[k].length()
            if s<=offset+length or k==len(self.pieces)-1:
                return k,min(1.,max(0.,(s-offset)/length))
        raise AssertionError('PATH_WINDOW_LOCATE_FAILED')

    def point_at(self,t):
        _parameter(t);self.validate()
        k,local=self._locate(t)
        q=self.pieces[k].point_at(local)
        fraction=.5 if t==.5 else sin(pi*t/2)**2
        return Point3D(q.x,q.y,(1-fraction)*self.z_start+fraction*self.z_end)

    def tangent_at(self,t):
        """d(position)/dt, NOT a unit vector (same convention as the others)."""
        _parameter(t);self.validate()
        k,local=self._locate(t)
        scale=self._run/self.pieces[k].length()
        dx,dy,_=self.pieces[k].tangent_at(local)
        dzdt=0. if t in (0.,1.) else self.delta_z*(pi/2)*sin(pi*t)
        return dx*scale,dy*scale,dzdt

    @property
    def start(self):
        return self.point_at(0.)

    @property
    def end(self):
        return self.point_at(1.)

    def _z_s(self,t):
        return (self.delta_z/self._run)*(pi/2)*sin(pi*t)

    def _z_ss(self,t):
        return (self.delta_z/(self._run*self._run))*(pi*pi/2)*cos(pi*t)

    def _curvature_for(self,t,kappa_xy):
        zs=self._z_s(t);zss=self._z_ss(t)
        numerator=sqrt(kappa_xy*kappa_xy*(1.+zs*zs)+zss*zss)
        denominator=(1.+zs*zs)**1.5
        value=numerator/denominator
        _finite(value)
        return value if value>0 else 0.

    def curvature_at(self,t):
        """Exact kappa_3D at parameter t (1/mm) by the closed form above.

        At a piece boundary this returns the value of the piece the parameter
        resolves to; use curvature_candidates_at() to see every piece that
        shares a parameter, because the planar curvature JUMPS there."""
        _parameter(t);self.validate()
        k,_=self._locate(t)
        return self._curvature_for(t,self.piece_curvature(k))

    def curvature_candidates_at(self,t):
        """Every closed-form curvature at t, one per piece whose closed
        parameter interval contains t (so two values at an interior boundary)."""
        _parameter(t);self.validate()
        rows=[]
        for k in range(len(self.pieces)):
            lo=self._offsets[k]/self._run
            hi=(self._offsets[k]+self.pieces[k].length())/self._run
            if lo-1e-12<=t<=hi+1e-12:
                kappa=self.piece_curvature(k)
                rows.append((kappa,self._curvature_for(t,kappa)))
        if not rows:
            k,_=self._locate(t)
            kappa=self.piece_curvature(k)
            rows.append((kappa,self._curvature_for(t,kappa)))
        return rows

    def radius_of_curvature_at(self,t):
        value=self.curvature_at(t)
        return float('inf') if value==0 else 1./value

    def curvature_breakpoints(self):
        """Every parameter where the exact maximum must be checked: the piece
        boundaries plus the two window ends."""
        self.validate()
        rows=[0.]
        for offset in self._offsets[1:]:
            rows.append(offset/self._run)
        rows.append(1.)
        return tuple(rows)

    def max_curvature(self):
        """EXACT maximum of kappa_3D over the whole window (1/mm).

        Evaluated at every piece boundary with EVERY piece that shares that
        parameter, because a line-to-arc boundary is a jump of the planar
        curvature and the larger side is the binding one. Inside a single piece
        the closed form is monotone away from its middle, so these finitely
        many values are the exact maximum."""
        self.validate()
        value=max(value for t in self.curvature_breakpoints()
                  for _,value in self.curvature_candidates_at(t))
        _finite(value)
        return value

    def minimum_curvature_radius(self):
        """mm; exact 1/max_curvature over the whole window, never a sample min."""
        value=self.max_curvature()
        return float('inf') if value==0 else 1./value
    def curvature_certificate(self):
        """Machine-readable proof record: the exact maximum and where it is hit."""
        self.validate()
        rows=[]
        for t in self.curvature_breakpoints():
            for kappa_xy,value in self.curvature_candidates_at(t):
                rows.append(dict(parameter=t,piece_planar_curvature=kappa_xy,
                                 curvature_per_mm=value,
                                 radius_mm=(float('inf') if value<=0 else 1./value)))
        worst=max(rows,key=lambda r:r['curvature_per_mm'])
        radius=(float('inf') if worst['curvature_per_mm']<=0
                else 1./worst['curvature_per_mm'])
        return dict(method='ANALYTIC_CLOSED_FORM_MAX_AT_PIECE_BOUNDARIES',
                    formula='sqrt(kappa_xy^2*(1+z_s^2)+z_ss^2)/(1+z_s^2)^1.5',
                    planar_run_mm=self._run,delta_z_mm=self.delta_z,
                    piece_count=len(self.pieces),
                    piece_planar_curvatures=[self.piece_curvature(k)
                                             for k in range(len(self.pieces))],
                    breakpoint_parameters=list(self.curvature_breakpoints()),
                    per_breakpoint=rows,
                    maximum_curvature_per_mm=worst['curvature_per_mm'],
                    minimum_curvature_radius_mm=radius,
                    attained_at_parameter=worst['parameter'],
                    argument=('inside one piece kappa_xy is constant, 1+z_s^2 increases and '
                              'the absolute z_ss decreases on [0,1/2], and the profile is '
                              'symmetric about 1/2, so the maximum over a piece is attained '
                              'at one of its two ends'))

    def length(self,abs_tol=1e-10,rel_tol=1e-12,max_depth=20):
        """Adaptive Simpson arc length of speed(t)=hypot(L,(pi|dz|/2) sin(pi t)).

        The XY speed is the planar arc-length rate L, because XY follows the
        frozen planar path at unit planar-arc-length speed; the shared cosine
        phase adds the vertical component. Nonconvergence raises instead of
        returning an unchecked estimate.
        """
        self.validate();_finite(abs_tol,rel_tol)
        if abs_tol<=0 or rel_tol<0 or type(max_depth) is not int or not 0<=max_depth<=30:
            raise ValueError('Invalid integration tolerance/depth.')
        run=self._run;amplitude=abs(self.delta_z)*(pi/2)
        def speed(t):return hypot(run,amplitude*sin(pi*t))
        a,b=0.,1.;fa,fb,fm=speed(a),speed(b),speed(.5)
        whole=(fa+4*fm+fb)/6
        budget=abs_tol+rel_tol*whole
        _finite(whole,budget)
        def refine(a,b,fa,fm,fb,whole,budget,depth):
            m=(a+b)/2;fl=speed((a+m)/2);fr=speed((m+b)/2)
            left=(m-a)*(fa+4*fl+fm)/6;right=(b-m)*(fm+4*fr+fb)/6
            difference=left+right-whole
            if abs(difference)<=15*budget:return left+right+difference/15
            if depth==0:raise RuntimeError('TRANSITION_LENGTH_NOT_CONVERGED')
            return fsum((refine(a,m,fa,fl,fm,left,budget/2,depth-1),
                         refine(m,b,fm,fr,fb,right,budget/2,depth-1)))
        value=refine(a,b,fa,fm,fb,whole,budget,max_depth)
        _finite(value)
        return value


TRANSITION_TYPES=(CosineTransition3D,PathWindowTransition3D)
PLANAR_FIXED_Z_TYPES=(LineSegment3D,PlanarArcSegment3D)


Primitive3D = LineSegment3D | PlanarArcSegment3D | CosineTransition3D | PathWindowTransition3D


@dataclass(frozen=True)
class Route3D:
    route_id: int
    primitives: tuple[Primitive3D,...]
    continuity_tol: float = 1e-9

    def __post_init__(self):
        object.__setattr__(self,'primitives',tuple(deepcopy(self.primitives)))
        self.validate()

    def validate(self):
        _finite(self.continuity_tol)
        if type(self.route_id) is not int or self.continuity_tol<0:
            raise ValueError('Invalid route id/continuity tolerance.')
        for i,p in enumerate(self.primitives):
            if not isinstance(p,(LineSegment3D,PlanarArcSegment3D,CosineTransition3D,PathWindowTransition3D)):
                raise TypeError('Unsupported 3D primitive.')
            p.validate()
            if i and not self.primitives[i-1].end.is_close(p.start,self.continuity_tol):
                raise ValueError('DISCONTINUOUS_ROUTE_3D')

    @property
    def start_point(self):
        self.validate()
        return _copy_point(self.primitives[0].start) if self.primitives else None

    @property
    def end_point(self):
        self.validate()
        return _copy_point(self.primitives[-1].end) if self.primitives else None

    def total_length(self):
        self.validate()
        value=fsum(p.length() for p in self.primitives)
        _finite(value)
        return value


def lift_smoothed_route_to_layer(route: SmoothedRoute2D,layer: Layer) -> Route3D:
    """Read-only exact Line/Arc lifting. No allocation or sampled geometry."""
    if not isinstance(route,SmoothedRoute2D) or not isinstance(layer,Layer):
        raise TypeError('Expected SmoothedRoute2D and Layer.')
    layer.validate();validate_smoothed_route_2d(route)
    result=[]
    for s in route.segments:
        if isinstance(s,LineSegment2D):
            result.append(LineSegment3D(Point3D(s.start.x,s.start.y,layer.z_mm),
                                        Point3D(s.end.x,s.end.y,layer.z_mm)))
        elif isinstance(s,ArcSegment2D):
            arc=PlanarArcSegment3D(s.center.x,s.center.y,layer.z_mm,arc_segment_radius(s),
                atan2(s.start.y-s.center.y,s.start.x-s.center.x),s.sweep_rad)
            object.__setattr__(arc,'_source_start_xy',(s.start.x,s.start.y))
            object.__setattr__(arc,'_source_end_xy',(s.end.x,s.end.y))
            result.append(arc)
    return Route3D(route.waveguide_id,tuple(result))
