"""Bounded centerline clearance for the project's three 3D primitives.

No width, layer pitch, routing or manufacturing standard is inferred.
Analytic geometric bounds include an explicit absolute floating guard (tol).
"""
from dataclasses import dataclass,asdict
from math import atan2,cos,sin,pi,tau,hypot,fsum,inf
from heapq import heappush,heappop
from itertools import combinations
from .models import Point2D,Point3D,LineSegment2D,ArcSegment2D
from .geometry_3d import (LineSegment3D,PlanarArcSegment3D,CosineTransition3D,
    PathWindowTransition3D,Route3D,_finite)
from .collision import find_segment_intersections_2d
from .geometry_3d_diagnostics import validate_tangent_join_3d

TYPES=(LineSegment3D,PlanarArcSegment3D,CosineTransition3D,PathWindowTransition3D)
# Declared constant of the adjacent-join policy: a primitive is only certified
# from the parameter at which its ARC LENGTH to the shared joint reaches
# ADJACENT_FAR_MULTIPLE x clearance. The unavoidable local neighbourhood is
# therefore smaller than 2 x ADJACENT_FAR_MULTIPLE x clearance of arc length,
# and the nearest pair the certification has to clear is one full
# ADJACENT_FAR_MULTIPLE x clearance away from the joint on one side only.
ADJACENT_FAR_MULTIPLE=2.0


def _xyz(p):return p.x,p.y,p.z
def _sub(a,b):return tuple(x-y for x,y in zip(a,b))
def _dot(a,b):return fsum(x*y for x,y in zip(a,b))
def _cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def _clamp(t):return max(0.,min(1.,t))
def _lerp(a,b,t):return Point3D(*((1-t)*x+t*y for x,y in zip(_xyz(a),_xyz(b))))


def _settings(clearance,tol,distance_tol,max_subdivisions):
    _finite(clearance,tol,distance_tol)
    if clearance<0 or tol<=0 or distance_tol<2*tol or type(max_subdivisions) is not int or max_subdivisions<0:
        raise ValueError('Require clearance>=0, tol>0, distance_tol>=2*tol, integer budget>=0.')


def _valid(p):
    if type(p) not in TYPES:raise TypeError('Unsupported primitive.')
    p.validate();p.start.validate();p.end.validate()


@dataclass(frozen=True)
class Distance3D:
    distance_mm: float
    closest_point_a: Point3D
    closest_point_b: Point3D
    parameter_a: float
    parameter_b: float
    lower_bound_mm: float
    upper_bound_mm: float
    error_bound_mm: float
    converged: bool
    subdivision_count: int
    method: str
    intersection_status: str
    xy_intersection_kinds: tuple = ()


def _result(a,b,s,t,d,lower,upper,method,converged=True,count=0,kinds=(),intersection=None):
    pa,pb=a.point_at(s),b.point_at(t)
    _finite(d,lower,upper,s,t)
    if intersection is None:
        intersection='INTERSECTING_WITNESS' if pa==pb else 'DISJOINT' if lower>0 else 'UNRESOLVED'
    return Distance3D(d,pa,pb,s,t,lower,upper,max(d-lower,upper-d),converged,count,method,intersection,tuple(kinds))


def _line_closest(p0,p1,q0,q1):
    """Finite segment active sets: four edges plus interior stationary point.

    Parallel cases need only edges. Cross-product denominator avoids 1-dot²
    cancellation for nearly parallel directions. Internal zero chords allowed.
    """
    u=_sub(_xyz(p1),_xyz(p0));v=_sub(_xyz(q1),_xyz(q0));w=_sub(_xyz(q0),_xyz(p0))
    lu,lv=hypot(*u),hypot(*v)
    un=tuple(x/lu for x in u) if lu else (0.,0.,0.)
    vn=tuple(x/lv for x in v) if lv else (0.,0.,0.)
    candidates=[]
    for s in (0.,1.):
        p=_lerp(p0,p1,s)
        t=_clamp(_dot(_sub(_xyz(p),_xyz(q0)),vn)/lv) if lv else 0.
        candidates.append((s,t))
    for t in (0.,1.):
        q=_lerp(q0,q1,t)
        s=_clamp(_dot(_sub(_xyz(q),_xyz(p0)),un)/lu) if lu else 0.
        candidates.append((s,t))
    n=_cross(un,vn);nn=_dot(n,n)
    if nn>0 and lu and lv:
        s=_dot(_cross(w,vn),n)/nn/lu
        t=_dot(_cross(w,un),n)/nn/lv
        if 0<=s<=1 and 0<=t<=1:candidates.append((s,t))
    values=[(_lerp(p0,p1,s).distance_to(_lerp(q0,q1,t)),s,t) for s,t in candidates]
    return min(values)


def line_line_minimum_distance_3d(a,b,*,tol=1e-9):
    _finite(tol)
    if tol<=0:raise ValueError('Positive numerical tolerance required.')
    if type(a) is not LineSegment3D or type(b) is not LineSegment3D:raise TypeError('Expected lines.')
    _valid(a);_valid(b)
    d,s,t=_line_closest(a.start,a.end,b.start,b.end)
    return _result(a,b,s,t,d,max(0.,d-tol),d+tol,'ANALYTIC_LINE_LINE')


def fixed_z(p):
    """Exact fixed-z recognition, never flatten a sloping line by tolerance."""
    if type(p) is PlanarArcSegment3D:return p.z
    if type(p) is LineSegment3D and p.start.z==p.end.z:return p.start.z
    return None


def fixed_layer_clearance_certificate(a,b,clearance_mm,*,tol=1e-9):
    """O(1) classification certificate only: gap is a LOWER BOUND, not d_min."""
    _finite(clearance_mm,tol)
    if clearance_mm<0 or tol<=0:raise ValueError('Invalid clearance/tolerance.')
    _valid(a);_valid(b);za,zb=fixed_z(a),fixed_z(b)
    if za is not None and zb is not None and abs(za-zb)>=clearance_mm+tol:
        return dict(status='CLEAR_BY_LAYER_SEPARATION',distance_lower_bound_mm=abs(za-zb),
                    minimum_distance_mm=None,clearance_mm=clearance_mm)
    return None


def _project(p):
    a,b=p.start,p.end
    if type(p) is LineSegment3D:return LineSegment2D(Point2D(a.x,a.y),Point2D(b.x,b.y))
    return ArcSegment2D(Point2D(a.x,a.y),Point2D(b.x,b.y),Point2D(p.center_x,p.center_y),p.sweep_angle)


def _arc_parameter(p,x,y,tol):
    theta=atan2(y-p.center_y,x-p.center_x)
    delta=((theta-p.start_angle) if p.sweep_angle>0 else (p.start_angle-theta))%tau
    if tau-delta<=tol/p.radius:delta=0.
    if delta<=abs(p.sweep_angle)+tol/p.radius:return _clamp(delta/abs(p.sweep_angle))
    return None


def _parameter_xy(p,x,y,tol):
    if type(p) is PlanarArcSegment3D:return _arc_parameter(p,x,y,tol)
    if type(p) is PathWindowTransition3D:
        # Nearest XY point over the exact planar sub-curves; the returned
        # parameter is the whole-window parameter u in [0,1].
        best=None;total=p.planar_run_mm
        for k,piece in enumerate(p.pieces):
            local=_parameter_xy(piece,x,y,tol)
            for candidate in ([local] if local is not None else [0.,1.]):
                q=piece.point_at(candidate)
                d=hypot(q.x-x,q.y-y)
                if best is None or d<best[0]:
                    u=(p.piece_offsets[k]+candidate*piece.length())/total
                    best=(d,u)
        return None if best is None else best[1]
    dx,dy=p.end.x-p.start.x,p.end.y-p.start.y
    return _clamp(((x-p.start.x)*dx+(y-p.start.y)*dy)/(dx*dx+dy*dy))


def _point_candidates(p,point,tol):
    if type(p) is LineSegment3D:return [_parameter_xy(p,point.x,point.y,tol)]
    if type(p) is PathWindowTransition3D:
        values=[0.,1.]
        t=_parameter_xy(p,point.x,point.y,tol)
        if t is not None:values.append(t)
        return values
    values=[0.,1.]
    if point.x!=p.center_x or point.y!=p.center_y:
        t=_arc_parameter(p,point.x,point.y,tol)
        if t is not None:values.append(t)
    return values


def planar_primitive_minimum_distance(a,b,*,tol=1e-9):
    """Exact candidate enumeration in XY plus fixed dz; existing intersection kernel."""
    _finite(tol)
    if tol<=0:raise ValueError('Positive tolerance required.')
    _valid(a);_valid(b)
    if fixed_z(a) is None or fixed_z(b) is None:raise ValueError('Fixed-z primitives required.')
    events=find_segment_intersections_2d(_project(a),_project(b),tol)
    pairs=[]
    for s in (0.,1.):
        pairs.extend((s,t) for t in _point_candidates(b,a.point_at(s),tol))
    for t in (0.,1.):
        pairs.extend((s,t) for s in _point_candidates(a,b.point_at(t),tol))
    for e in events:
        if e.point is not None:
            s=_parameter_xy(a,e.point.x,e.point.y,tol);t=_parameter_xy(b,e.point.x,e.point.y,tol)
            if s is not None and t is not None:pairs.append((s,t))
    if type(a) is LineSegment3D and type(b) is LineSegment3D:
        _,s,t=_line_closest(a.start,a.end,b.start,b.end);pairs.append((s,t))
    elif type(a) is PlanarArcSegment3D and type(b) is PlanarArcSegment3D:
        dx,dy=b.center_x-a.center_x,b.center_y-a.center_y;length=hypot(dx,dy)
        if length:
            for sa in (-1,1):
                for sb in (-1,1):
                    s=_arc_parameter(a,a.center_x+sa*a.radius*dx/length,a.center_y+sa*a.radius*dy/length,tol)
                    t=_arc_parameter(b,b.center_x+sb*b.radius*dx/length,b.center_y+sb*b.radius*dy/length,tol)
                    if s is not None and t is not None:pairs.append((s,t))
        # Concentric arcs: endpoint-to-arc candidates cover shared angular range.
    else:
        line,arc=(a,b) if type(a) is LineSegment3D else (b,a)
        dx,dy=line.end.x-line.start.x,line.end.y-line.start.y;length=hypot(dx,dy)
        for sign in (-1,1):
            x,y=arc.center_x-sign*arc.radius*dy/length,arc.center_y+sign*arc.radius*dx/length
            u=_arc_parameter(arc,x,y,tol)
            v=((x-line.start.x)*dx+(y-line.start.y)*dy)/(length*length)
            if u is not None and 0<=v<=1:pairs.append((v,u) if line is a else (u,v))
    values=[]
    for s,t in pairs:
        pa,pb=a.point_at(s),b.point_at(t)
        values.append((pa.distance_to(pb),s,t))
    d,s,t=min(values)
    witness_distance=d
    gap=abs(fixed_z(a)-fixed_z(b));kinds=tuple(sorted({e.kind for e in events}))
    if events:
        # Current 2D exact kernel's tol-based CROSS/TOUCH/OVERLAP semantics.
        d=gap
    intersection='INTERSECTING_WITHIN_GEOMETRY_TOL' if events and gap==0 else None
    return _result(a,b,s,t,d,max(gap,d-tol),max(d,witness_distance)+tol,'ANALYTIC_PLANAR_XY_PLUS_Z',kinds=kinds,intersection=intersection)


def _box(p,u,v):
    if type(p) is PathWindowTransition3D:
        # Conservative XY box over the exact planar sub-curves actually covered
        # (arc extremal angles included by the piece-level recursion) and the
        # exact vertical range, which is monotone in the window parameter.
        boxes=[]
        total=p.planar_run_mm
        for k,piece in enumerate(p.pieces):
            lo=p.piece_offsets[k]/total
            hi=(p.piece_offsets[k]+piece.length())/total
            a=max(u,lo);b=min(v,hi)
            if b>a:
                boxes.append(_box(piece,(a-lo)/(hi-lo),(b-lo)/(hi-lo)))
        if not boxes:
            boxes=[_box(p.pieces[0],0.,1.)]
        zu,zv=p.point_at(u).z,p.point_at(v).z
        rows=[]
        for axis in range(3):
            if axis==2:
                rows.append((min(zu,zv),max(zu,zv)))
            else:
                rows.append((min(b[axis][0] for b in boxes),max(b[axis][1] for b in boxes)))
        return tuple(rows)
    points=[p.point_at(u),p.point_at(v)]
    if type(p) is PlanarArcSegment3D:
        for angle in (0.,pi/2,pi,3*pi/2):
            t=_arc_parameter(p,p.center_x+cos(angle)*p.radius,p.center_y+sin(angle)*p.radius,0.)
            if t is not None and u<t<v:points.append(p.point_at(t))
    return tuple((min(_xyz(q)[i] for q in points),max(_xyz(q)[i] for q in points)) for i in range(3))


def _box_distance(a,b):return hypot(*(max(0.,x[0]-y[1],y[0]-x[1]) for x,y in zip(a,b)))


def _chord_error(p,u,v):
    if type(p) is LineSegment3D:return 0.
    if type(p) is PathWindowTransition3D:
        # sup|r''(t)| for r(t) following the frozen planar path at arc-length
        # rate L: r'' = L^2*kappa*N + z_tt*ez with |z_tt| <= pi^2|dz|/2.
        run=p.planar_run_mm
        kappa=p.max_planar_curvature()
        m2=hypot(run*run*kappa,abs(p.delta_z)*pi*pi/2)
        value=m2*(v-u)**2/8
        _finite(value)
        return value
    m2=abs(p.delta_z)*pi*pi/2 if type(p) is CosineTransition3D else p.radius*p.sweep_angle**2
    value=m2*(v-u)**2/8
    if type(p) is PlanarArcSegment3D:
        # Lifted arcs retain source endpoint coordinates within the 2D tolerance.
        # Include their explicit deviation from the circle, not just C2 error.
        residual=[]
        for t in (u,v):
            angle=p.start_angle+t*p.sweep_angle
            exact=Point3D(p.center_x+p.radius*cos(angle),p.center_y+p.radius*sin(angle),p.z)
            residual.append(exact.distance_to(p.point_at(t)))
        value+=max(residual)
    _finite(value)
    return value


def adaptive_primitive_minimum_distance(a,b,*,tol=1e-9,distance_tol=1e-6,max_subdivisions=4096,
                                      a_range=(0.,1.),b_range=(0.,1.)):
    """Branch-and-bound rectangles; geometric chord error <= sup|r''| dt²/8.

    Lower = max(AABB lower, chord distance - both curve errors) - tol.
    Upper = distance between actual curve points at chord-minimizer parameters + tol.
    Only lower/upper convergence is accepted, never midpoint flatness alone.
    a_range/b_range restrict the search to a parameter rectangle; the default
    (0,1)x(0,1) is the historical whole-primitive call and is unchanged.
    """
    _settings(0,tol,distance_tol,max_subdivisions);_valid(a);_valid(b)
    _finite(a_range[0],a_range[1],b_range[0],b_range[1])
    if not (0.<=a_range[0]<a_range[1]<=1. and 0.<=b_range[0]<b_range[1]<=1.):
        raise ValueError('INVALID_PARAMETER_RANGE')
    heap=[];serial=0;best=(inf,0.,0.);splits=0
    def node(u,v,x,y):
        nonlocal serial,best
        d,s,t=_line_closest(a.point_at(u),a.point_at(v),b.point_at(x),b.point_at(y))
        sa=u+s*(v-u);tb=x+t*(y-x)
        actual=a.point_at(sa).distance_to(b.point_at(tb))
        best=min(best,(actual,sa,tb))
        # Additional actual witness only; midpoint NEVER supplies a safety bound.
        ma,mb=(u+v)/2,(x+y)/2
        best=min(best,(a.point_at(ma).distance_to(b.point_at(mb)),ma,mb))
        ea,eb=_chord_error(a,u,v),_chord_error(b,x,y)
        lower=max(0.,max(_box_distance(_box(a,u,v),_box(b,x,y)),d-ea-eb)-tol)
        serial+=1
        heappush(heap,(lower,serial,u,v,x,y,ea,eb))
    node(a_range[0],a_range[1],b_range[0],b_range[1])
    while heap:
        lower=heap[0][0];upper=best[0]+tol
        if upper-lower<=distance_tol:break
        if splits>=max_subdivisions:break
        _,_,u,v,x,y,ea,eb=heappop(heap)
        if ea>=eb and ea>0:
            m=(u+v)/2
            if m==u or m==v:raise ValueError('Subdivision parameter resolution exhausted.')
            node(u,m,x,y);node(m,v,x,y)
        elif eb>0:
            m=(x+y)/2
            if m==x or m==y:raise ValueError('Subdivision parameter resolution exhausted.')
            node(u,v,x,m);node(u,v,m,y)
        else:break
        splits+=1
        # Pruned cells cannot beat a known actual witness; preserve all others.
        while heap and heap[0][0]>best[0]+tol:heappop(heap)
    lower=min(heap[0][0],best[0]+tol) if heap else max(0.,best[0]-tol)
    d,s,t=best;upper=d+tol
    return _result(a,b,s,t,d,lower,upper,'ADAPTIVE_CHORD_BOUNDS',upper-lower<=distance_tol,splits)


def classify_distance(distance,clearance_mm,*,tol=1e-9):
    if not distance.converged:return 'DISTANCE_NOT_CONVERGED'
    if distance.method.startswith('ANALYTIC') and abs(distance.distance_mm-clearance_mm)<=tol:
        return 'TOUCHING_THRESHOLD'
    if distance.distance_mm-distance.error_bound_mm>=clearance_mm:return 'CLEAR'
    if distance.distance_mm+distance.error_bound_mm<clearance_mm:return 'COLLISION'
    return 'AMBIGUOUS_CLEARANCE'


def analyze_primitive_clearance(a,b,clearance_mm,*,tol=1e-9,distance_tol=1e-6,max_subdivisions=4096):
    _settings(clearance_mm,tol,distance_tol,max_subdivisions)
    result=dict(primitive_a_type=type(a).__name__,primitive_b_type=type(b).__name__,clearance_mm=clearance_mm)
    try:
        _valid(a);_valid(b)
        certificate=fixed_layer_clearance_certificate(a,b,clearance_mm,tol=tol)
        if fixed_z(a) is not None and fixed_z(b) is not None:
            d=planar_primitive_minimum_distance(a,b,tol=tol)
        elif type(a) is LineSegment3D and type(b) is LineSegment3D:
            d=line_line_minimum_distance_3d(a,b,tol=tol)
        else:d=adaptive_primitive_minimum_distance(a,b,tol=tol,distance_tol=distance_tol,max_subdivisions=max_subdivisions)
        result.update(asdict(d),minimum_distance_mm=d.distance_mm,margin_mm=d.distance_mm-clearance_mm,
                      status=classify_distance(d,clearance_mm,tol=tol),layer_certificate=certificate)
        if certificate is not None:result['status']='CLEAR'
    except (ValueError,TypeError,OverflowError,ZeroDivisionError) as ex:
        result.update(status='INVALID_GEOMETRY',minimum_distance_mm=None,margin_mm=None,detail=str(ex))
    return result


def _aggregate(records,clearance):
    priority=('COLLISION','INVALID_GEOMETRY','DISTANCE_NOT_CONVERGED','AMBIGUOUS_CLEARANCE','TOUCHING_THRESHOLD')
    status=next((s for s in priority if any(r['status']==s for r in records)),'CLEAR')
    valid=[r for r in records if r.get('minimum_distance_mm') is not None]
    if not valid:return dict(status=status,minimum_distance_mm=None,minimum_distance_scope='NO_EVALUATED_PAIRS')
    best=min(valid,key=lambda r:(r['minimum_distance_mm'],r['primitive_a_index'],r['primitive_b_index']))
    lower=min(r['lower_bound_mm'] for r in valid);upper=min(r['upper_bound_mm'] for r in valid)
    identities=[(r['primitive_a_index'],r['primitive_b_index']) for r in valid if r['lower_bound_mm']<=upper]
    invalid=any(r['status']=='INVALID_GEOMETRY' for r in records)
    intersection=('INTERSECTING' if any(r['intersection_status'].startswith('INTERSECTING') for r in valid)
                  else 'DISJOINT' if lower>0 and not invalid else 'UNRESOLVED')
    return dict(status=status,minimum_distance_mm=best['minimum_distance_mm'],margin_mm=best['margin_mm'],
        lower_bound_mm=None if invalid else lower,upper_bound_mm=upper,
        error_bound_mm=None if invalid else max(best['minimum_distance_mm']-lower,upper-best['minimum_distance_mm']),
        primitive_a_index=best['primitive_a_index'],primitive_b_index=best['primitive_b_index'],
        closest_point_a=best['closest_point_a'],closest_point_b=best['closest_point_b'],
        parameter_a=best['parameter_a'],parameter_b=best['parameter_b'],
        minimum_primitive_candidates=identities,minimum_primitive_identity_certified=len(identities)==1 and not invalid,
        minimum_distance_scope='INCOMPLETE_INVALID_GEOMETRY' if invalid else 'ALL_EVALUATED_PAIRS',
        intersection_status=intersection)


def analyze_route3d_clearance(route_a,route_b,clearance_mm,**kwargs):
    _settings(clearance_mm,kwargs.get('tol',1e-9),kwargs.get('distance_tol',1e-6),kwargs.get('max_subdivisions',4096))
    try:
        if not isinstance(route_a,Route3D) or not isinstance(route_b,Route3D):raise TypeError('Expected Route3D.')
        route_a.validate();route_b.validate()
        if not route_a.primitives or not route_b.primitives:raise ValueError('Empty route has no distance witness.')
    except (TypeError,ValueError,OverflowError) as ex:return dict(status='INVALID_GEOMETRY',detail=str(ex),minimum_distance_mm=None)
    records=[]
    for i,a in enumerate(route_a.primitives):
        for j,b in enumerate(route_b.primitives):
            r=analyze_primitive_clearance(a,b,clearance_mm,**kwargs)
            r.update(primitive_a_index=i,primitive_b_index=j);records.append(r)
    return dict(route_a_id=route_a.route_id,route_b_id=route_b.route_id,clearance_mm=clearance_mm,
                pair_results=records,**_aggregate(records,clearance_mm))


def _monotone_axis(p,axis):
    if _xyz(p.start)[axis]==_xyz(p.end)[axis]:return False
    if type(p) is PathWindowTransition3D:
        # A path window may follow an arc that turns back; it is monotone only
        # when EVERY piece is monotone in the same direction as the whole window.
        overall=_xyz(p.end)[axis]-_xyz(p.start)[axis]
        for piece in p.pieces:
            if not _monotone_axis(piece,axis):return False
            delta=_xyz(piece.end)[axis]-_xyz(piece.start)[axis]
            if delta*overall<=0:return False
        return True
    if type(p) is PlanarArcSegment3D:
        if axis==2:return False
        angles=(0.,pi) if axis==0 else (pi/2,3*pi/2)
        for angle in angles:
            t=_arc_parameter(p,p.center_x+p.radius*cos(angle),p.center_y+p.radius*sin(angle),0.)
            if t is not None and 0<t<1:return False
    return True


def _arc_length_lower_bound_to_end(p,s):
    """Lower bound of the arc length from parameter s to the end of primitive p.

    Lines and arcs are parameterised by arc length, so the bound is exact for
    them. A cosine transition or a path window has speed >= its PLANAR run, so
    (1-s)*planar_run (or (1-s)*lxy) is a valid lower bound."""
    _finite(s)
    if type(p) is CosineTransition3D:return (1.-s)*p.lxy
    if type(p) is PathWindowTransition3D:return (1.-s)*p.planar_run_mm
    return (1.-s)*p.length()


def _arc_length_lower_bound_from_start(p,t):
    _finite(t)
    if type(p) is CosineTransition3D:return t*p.lxy
    if type(p) is PathWindowTransition3D:return t*p.planar_run_mm
    return t*p.length()


def _adjacent_c1_arc_length_cap(a,b,tol,clearance_mm,angle_tol=1e-9,distance_tol=1e-6,
                                max_subdivisions=4096):
    """Extra-contact proof for a C0+C1 joint of a route that contains a PATH window.

    Declared policy: two points of ONE continuous centerline whose distance
    ALONG the route to their shared joint is smaller than the clearance are the
    same physical neighbourhood, not a self-approach. Every pair of points whose
    arc-length distance to the joint is at least the clearance on BOTH sides is
    certified by the same conservative branch-and-bound bound used elsewhere:
    the two rectangles {a in [0,s_cut]} x {b full} and {a full} x {b in [t_cut,1]},
    where s_cut/t_cut are the (lower-bound) parameters at arc-length clearance
    from the joint. If both rectangles are certified CLEAR, no pair of points
    further than the clearance apart along the route can be closer than the
    clearance in space. Returns None when the joint is not C1 or a rectangle is
    not certified, so the caller keeps its historical answer.
    """
    if a.end.distance_to(b.start)>tol:
        return dict(status='INVALID_GEOMETRY',detail='Disconnected adjacency')
    report=validate_tangent_join_3d(a,b,position_tol=tol,angle_tol=angle_tol)
    if not (report.position_continuous and report.tangent_continuous):
        return None
    far=ADJACENT_FAR_MULTIPLE*clearance_mm
    rectangles=[]
    run_a=_arc_length_lower_bound_to_end(a,0.)
    run_b=_arc_length_lower_bound_from_start(b,1.)
    if run_a>far:
        s_cut=1.-far/run_a
        if s_cut>0.:
            rectangles.append(((0.,s_cut),(0.,1.),'A_FAR_FROM_JOINT_VS_FULL_B'))
    if run_b>far:
        t_cut=far/run_b
        if t_cut<1.:
            rectangles.append(((0.,1.),(t_cut,1.),'FULL_A_VS_B_FAR_FROM_JOINT'))
    if not rectangles:
        return None
    checks=[]
    for a_range,b_range,label in rectangles:
        try:
            distance=adaptive_primitive_minimum_distance(a,b,tol=tol,distance_tol=distance_tol,
                max_subdivisions=max_subdivisions,a_range=a_range,b_range=b_range)
            status=classify_distance(distance,clearance_mm,tol=tol)
        except (ValueError,TypeError,OverflowError,ZeroDivisionError) as ex:
            return None
        checks.append(dict(region=label,a_range=list(a_range),b_range=list(b_range),
                           status=status,minimum_distance_mm=distance.distance_mm,
                           lower_bound_mm=distance.lower_bound_mm,
                           upper_bound_mm=distance.upper_bound_mm))
        if status=='COLLISION':
            return dict(status='COLLISION',detail='Extra adjacent contact outside the arc-length cap',
                        arc_length_cap_mm=clearance_mm,region_checks=checks)
        if status!='CLEAR':
            return None
    return dict(status='ADJACENT_JOIN_EXEMPT',proof='C1_CONTINUOUS_JOINT_OUTSIDE_ARC_LENGTH_CAP',
                arc_length_cap_mm=clearance_mm,adjacent_far_arc_length_mm=far,
                exempt_pair_arc_length_below_mm=2.*far,positive_clearance_evaluated=False,
                region_checks=checks)


def _adjacent_contact(a,b,tol,clearance_mm=None):
    """Exempt ONLY normal contact; detect extra planar events or prove separation.

    Positive clearance is not defined arbitrarily close to a connected joint.
    Unproved nonplanar adjacency is ambiguous, never silently skipped as clear.
    """
    if a.end.distance_to(b.start)>tol:return dict(status='INVALID_GEOMETRY',detail='Disconnected adjacency')
    if fixed_z(a) is not None and fixed_z(a)==fixed_z(b):
        events=find_segment_intersections_2d(_project(a),_project(b),tol)
        extra=[e for e in events if e.point is None or hypot(e.point.x-a.end.x,e.point.y-a.end.y)>tol]
        if extra:return dict(status='COLLISION',detail='Additional adjacent intersection/overlap',extra_event_kinds=[e.kind for e in extra])
        return dict(status='ADJACENT_JOIN_EXEMPT',proof='2D_EXACT_CONTACTS',positive_clearance_evaluated=False)
    for axis in range(3):
        if _monotone_axis(a,axis) and _monotone_axis(b,axis):
            da=_xyz(a.end)[axis]-_xyz(a.start)[axis];db=_xyz(b.end)[axis]-_xyz(b.start)[axis]
            if da*db>0:
                return dict(status='ADJACENT_JOIN_EXEMPT',proof='STRICT_MONOTONE_SEPARATING_COORDINATE',axis=axis,positive_clearance_evaluated=False)
    if clearance_mm is not None and (type(a) is PathWindowTransition3D or type(b) is PathWindowTransition3D):
        proven=_adjacent_c1_arc_length_cap(a,b,tol,clearance_mm)
        if proven is not None:return proven
    return dict(status='AMBIGUOUS_CLEARANCE',detail='Adjacent nonplanar extra-contact exclusion not proved',positive_clearance_evaluated=False)


def analyze_route3d_self_clearance(route,clearance_mm,**kwargs):
    _settings(clearance_mm,kwargs.get('tol',1e-9),kwargs.get('distance_tol',1e-6),kwargs.get('max_subdivisions',4096))
    try:route.validate()
    except (ValueError,TypeError,AttributeError):return dict(status='INVALID_GEOMETRY',minimum_distance_mm=None)
    records=[];adjacent=[]
    for i,j in combinations(range(len(route.primitives)),2):
        a,b=route.primitives[i],route.primitives[j]
        if j==i+1:
            try:
                _valid(a);_valid(b)
                r=_adjacent_contact(a,b,kwargs.get('tol',1e-9),clearance_mm)
            except (TypeError,ValueError,OverflowError):r=dict(status='INVALID_GEOMETRY')
            r.update(primitive_a_index=i,primitive_b_index=j)
            adjacent.append(r)
        else:
            r=analyze_primitive_clearance(a,b,clearance_mm,**kwargs);r.update(primitive_a_index=i,primitive_b_index=j);records.append(r)
    aggregate=_aggregate(records+[r for r in adjacent if r['status']!='ADJACENT_JOIN_EXEMPT'],clearance_mm)
    return dict(route_id=route.route_id,clearance_mm=clearance_mm,pair_results=records,adjacent_results=adjacent,
        self_clearance_policy='NONADJACENT_CLEARANCE_PLUS_ADJACENT_EXTRA_CONTACT_CHECK',**aggregate)
