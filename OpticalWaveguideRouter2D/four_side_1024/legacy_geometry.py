"""Four-side geometry adapter of the reverse-engineered AutoRouter formulas.

This module does no path search.  A caller supplies the first-free legacy track.
Opposite-side geometry follows ``wiring_bend_826.plotter_bend`` including its
short-S branch for dx < 2R.  Adjacent sides require an additional orthogonal
template because rigid rotation cannot turn opposing port normals into
perpendicular port normals.  Geometry is kept at full precision rather than
the original workbook's four decimal places.
"""
from __future__ import annotations

import math

import numpy as np

from .geometry import validate

BOARD = 150.
TOL = 1e-8
INWARD = {'S': (0.,1.), 'N': (0.,-1.), 'E': (-1.,0.), 'W': (1.,0.)}


def _point(value):
    point = np.asarray(value,dtype=float)
    if point.shape != (2,) or not np.all(np.isfinite(point)):
        raise ValueError('Expected finite (x,y) point')
    return point


def _line(p0,p1):
    return dict(kind='line',p0=list(map(float,p0)),p1=list(map(float,p1)),layer=0)


def _arc(p0,p1,center,radius,angle,sweep):
    return dict(kind='arc',p0=list(map(float,p0)),p1=list(map(float,p1)),
                center=list(map(float,center)),radius=float(radius),
                start_angle=float(angle),sweep=float(sweep),layer=0)


def _append_line(result,p0,p1):
    if np.linalg.norm(np.asarray(p1)-p0)>1e-10:
        result.append(_line(p0,p1))


def _check(result,p,q,start_dir,end_dir,radius,width):
    errors=validate(result,p,q,start_dir,end_dir,board=BOARD,width=width,min_radius=radius)
    if errors:
        raise ValueError('Invalid legacy geometry: '+', '.join(errors))
    return result


def opposite(p,q,track,radius=5.,width=.05):
    """Legacy opposite-side two-bend path, canonical S -> N.

    ``p=(sx,0)``, ``q=(tx,150)``; the rectangular parent path is
    ``[p,(sx,track),(tx,track),q]``.  With dx < 2R, the two short arcs
    still have radius R: theta=acos(1-dx/(2R)), h=R*sin(theta).
    Insufficient room is rejected; the radius is never reduced.
    """
    p,q=_point(p),_point(q)
    if not math.isfinite(radius) or radius<=0 or not math.isfinite(track):
        raise ValueError('Finite positive radius and finite track required')
    if abs(p[1])>TOL or abs(q[1]-BOARD)>TOL:
        raise ValueError('opposite requires canonical S -> N boundary endpoints')
    dx=abs(float(q[0]-p[0]))
    if dx<TOL:
        return _check([_line(p,q)],p,q,(0,1),(0,1),radius,width)
    sign=1. if q[0]>p[0] else -1.
    theta=math.pi/2 if dx>=2*radius else math.acos(1.-dx/(2*radius))
    height=radius if dx>=2*radius else radius*math.sin(theta)
    if track-height<p[1]-TOL or track+height>q[1]+TOL:
        raise ValueError('Insufficient longitudinal space for original legacy radius')
    first_start=np.array([p[0],track-height])
    first_end=np.array([p[0]+sign*min(radius,dx/2.),track])
    second_start=np.array([q[0]-sign*min(radius,dx/2.),track])
    second_end=np.array([q[0],track+height])
    first_center=np.array([p[0]+sign*radius,track-height])
    second_center=np.array([q[0]-sign*radius,track+height])
    first_angle=math.pi if sign>0 else 0.
    second_angle=-theta if sign>0 else math.pi+theta
    result=[]
    _append_line(result,p,first_start)
    result.append(_arc(first_start,first_end,first_center,radius,first_angle,-sign*theta))
    _append_line(result,first_end,second_start)
    result.append(_arc(second_start,second_end,second_center,radius,second_angle,sign*theta))
    _append_line(result,second_end,q)
    return _check(result,p,q,(0,1),(0,1),radius,width)


def _orthogonal_quarters(points,radius):
    """The original dx >= 2R corner construction, with local segment checks.

    At each right-angle corner V, the two legacy tangent points are
    V+R*dir_in and V+R*dir_out, and the centre is V+R*(dir_in+dir_out).
    No short-S approximation is applied to a single corner or to three bends.
    """
    vertices=[]
    for value in points:
        point=_point(value)
        if vertices and np.linalg.norm(point-vertices[-1])<TOL:
            continue
        vertices.append(point)
        while len(vertices)>=3:
            a,b,c=vertices[-3:]
            u,v=b-a,c-b
            if abs(u[0]*v[1]-u[1]*v[0])>TOL:
                break
            if np.dot(u,v)<=0:
                raise ValueError('Orthogonal path reverses direction')
            vertices.pop(-2)
    if len(vertices)<2:
        raise ValueError('Empty orthogonal path')
    directions=[]
    for a,b in zip(vertices[:-1],vertices[1:]):
        delta=b-a
        if min(abs(delta[0]),abs(delta[1]))>TOL:
            raise ValueError('Only orthogonal legacy segments are accepted')
        directions.append(delta/np.linalg.norm(delta))
    for i,(a,b) in enumerate(zip(vertices[:-1],vertices[1:])):
        trim=radius*((i>0)+(i<len(vertices)-2))
        if np.linalg.norm(b-a)<trim-TOL:
            raise ValueError(f'Insufficient segment length for original radius: {i}')
    result=[]
    cursor=vertices[0]
    for i,vertex in enumerate(vertices[1:-1],1):
        dir_in=-directions[i-1]
        dir_out=directions[i]
        pin,pout=vertex+radius*dir_in,vertex+radius*dir_out
        center=vertex+radius*(dir_in+dir_out)
        cross=directions[i-1][0]*dir_out[1]-directions[i-1][1]*dir_out[0]
        angle=math.atan2(pin[1]-center[1],pin[0]-center[0])
        _append_line(result,cursor,pin)
        result.append(_arc(pin,pout,center,radius,angle,math.copysign(math.pi/2,cross)))
        cursor=pout
    _append_line(result,cursor,vertices[-1])
    return result


def adjacent(p,q,track,radius=5.,width=.05):
    """Necessary orthogonal adjacent-port extension, canonical S -> E.

    For track == q.y, use the single L [p,(p.x,q.y),q].  Otherwise use
    [p,(p.x,track),(145,track),(145,q.y),q].  Every corner uses the original
    radius-R quarter-circle construction.  Three-bend radius conflicts fail
    explicitly rather than invoking a different routing algorithm.
    """
    p,q=_point(p),_point(q)
    if not math.isfinite(radius) or radius<=0 or not math.isfinite(track):
        raise ValueError('Finite positive radius and finite track required')
    if abs(p[1])>TOL or abs(q[0]-BOARD)>TOL:
        raise ValueError('adjacent requires canonical S -> E boundary endpoints')
    if abs(track-q[1])<TOL:
        points=[p,(p[0],q[1]),q]
    else:
        points=[p,(p[0],track),(145.,track),(145.,q[1]),q]
    result=_orthogonal_quarters(points,radius)
    return _check(result,p,q,(0,1),(1,0),radius,width)


def canonicalize(source_side,target_side,p,q):
    """Map any ordered distinct side pair to S -> N or S -> E.

    Returns ``(p_canonical,q_canonical,transform,kind)``.  Transform is an
    ordinary JSON-compatible dict containing matrix and offset for world ->
    canonical coordinates.  A reflection is necessary for half the adjacent
    orientations.  Distances, widths and radii are invariant.
    """
    if source_side not in INWARD or target_side not in INWARD or source_side==target_side:
        raise ValueError('Two distinct N/S/E/W sides required')
    matrices={'S':([[1.,0.],[0.,1.]],[0.,0.]),
              'E':([[0.,1.],[-1.,0.]],[0.,150.]),
              'N':([[-1.,0.],[0.,-1.]],[150.,150.]),
              'W':([[0.,-1.],[1.,0.]],[150.,0.])}
    matrix,offset=map(np.asarray,matrices[source_side])
    target_inward=matrix@np.asarray(INWARD[target_side])
    reflected=bool(np.allclose(target_inward,(1.,0.)))
    if reflected:
        reflection=np.array([[-1.,0.],[0.,1.]])
        matrix,offset=reflection@matrix,reflection@offset+np.array([150.,0.])
        target_inward=reflection@target_inward
    kind='opposite' if np.allclose(target_inward,(0.,-1.)) else 'adjacent'
    transform=dict(matrix=matrix.tolist(),offset=offset.tolist(),reflected=reflected,
                   source_side=source_side,target_side=target_side)
    return (matrix@_point(p)+offset).tolist(),(matrix@_point(q)+offset).tolist(),transform,kind


def transform_primitives(primitives,transform,inverse=False):
    """Rigidly map line/arc geometry, reversing signed sweeps under reflection."""
    matrix=np.asarray(transform['matrix'],dtype=float)
    offset=np.asarray(transform['offset'],dtype=float)
    if inverse:
        matrix=matrix.T
        offset=-matrix@offset
    determinant=float(np.linalg.det(matrix))
    if not np.allclose(matrix.T@matrix,np.eye(2)) or abs(abs(determinant)-1.)>TOL:
        raise ValueError('Transform must preserve Euclidean distances')
    result=[]
    for primitive in primitives:
        mapped=dict(primitive)
        for field in ('p0','p1','center'):
            if field in primitive:
                mapped[field]=(matrix@_point(primitive[field])+offset).tolist()
        if primitive['kind']=='arc':
            angle=primitive['start_angle']
            unit=matrix@np.array([math.cos(angle),math.sin(angle)])
            mapped['start_angle']=math.atan2(unit[1],unit[0])
            mapped['sweep']=determinant*primitive['sweep']
        result.append(mapped)
    return result
