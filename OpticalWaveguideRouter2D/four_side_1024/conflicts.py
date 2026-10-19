"""Single-plane line/circular-arc collision and local crossing clearance.

Circular intersections, tangent directions and clearance decisions use the exact
primitives. Chordal geometry (bounded by ``sagitta``) is only a spatial broad
phase. A crossing excuses ONLY a local interval on BOTH participating curves;
the rest of either curve must clear the entire other curve. This deliberately
does not certify optical crossing fabrication or an out-of-plane port adapter.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import math
from typing import Any

import numpy as np

try:
    from shapely import LineString, STRtree
    HAS_SHAPELY = True
except ImportError:
    LineString = STRtree = None
    HAS_SHAPELY = False

TAU = 2.0 * math.pi
EPS = 1e-8


def _sub(a, b):
    return a[0] - b[0], a[1] - b[1]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1]


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _norm(a):
    return math.hypot(*a)


def _distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


@dataclass(frozen=True)
class _Primitive:
    kind: str
    p0: tuple
    p1: tuple
    center: tuple = (0., 0.)
    radius: float = 0.
    start: float = 0.
    sweep: float = 0.
    length: float = 0.
    bounds: tuple = (0., 0., 0., 0.)

    def parameter(self, point):
        if self.kind == 'line':
            d = _sub(self.p1, self.p0)
            return max(0., min(1., _dot(_sub(point, self.p0), d) / (self.length ** 2)))
        a = math.atan2(point[1] - self.center[1], point[0] - self.center[0])
        delta = ((a-self.start) if self.sweep > 0 else (self.start-a)) % TAU
        # Modulo wraps a start angle displaced by floating-point noise to 2pi.
        if TAU-delta < EPS:
            delta = 0.
        return max(0., min(1., delta / abs(self.sweep)))

    def contains_angle(self, a):
        d = ((a-self.start) if self.sweep > 0 else (self.start-a)) % TAU
        return d <= abs(self.sweep) + EPS or TAU-d < EPS

    def point(self, t):
        if self.kind == 'line':
            return (self.p0[0]+t*(self.p1[0]-self.p0[0]),
                    self.p0[1]+t*(self.p1[1]-self.p0[1]))
        a = self.start + t*self.sweep
        return self.center[0]+self.radius*math.cos(a), self.center[1]+self.radius*math.sin(a)

    def tangent(self, t):
        if self.kind == 'line':
            return ((self.p1[0]-self.p0[0])/self.length,
                    (self.p1[1]-self.p0[1])/self.length)
        a = self.start + t*self.sweep
        sign = 1. if self.sweep > 0 else -1.
        return -sign*math.sin(a), sign*math.cos(a)

    def clip(self, t0, t1):
        if t0 <= 0 and t1 >= 1:
            return self
        return _make_primitive(dict(kind=self.kind, p0=self.point(t0), p1=self.point(t1),
            center=self.center, radius=self.radius, start_angle=self.start+t0*self.sweep,
            sweep=(t1-t0)*self.sweep))


def _make_primitive(p):
    if p.get('layer', 0) != 0 or abs(float(p.get('z', 0))) > EPS:
        raise ValueError('All waveguide primitives must remain in layer=0, z=0')
    kind = p['kind']
    p0, p1 = tuple(map(float, p['p0'])), tuple(map(float, p['p1']))
    if len(p0) != 2 or len(p1) != 2:
        raise ValueError('Only two-dimensional primitive coordinates are accepted')
    if not all(math.isfinite(v) for v in (*p0,*p1)):
        raise ValueError('Nonfinite geometry')
    if kind == 'line':
        length = _distance(p0, p1)
        if length <= EPS:
            raise ValueError('Zero-length line')
        return _Primitive(kind, p0, p1, length=length,
                          bounds=(min(p0[0],p1[0]), min(p0[1],p1[1]),
                                  max(p0[0],p1[0]), max(p0[1],p1[1])))
    if kind != 'arc':
        raise ValueError('Unknown primitive kind: '+str(kind))
    c = tuple(map(float, p['center']))
    r, start, sweep = float(p['radius']), float(p['start_angle']), float(p['sweep'])
    if len(c) != 2 or r <= EPS or abs(sweep) <= EPS or abs(sweep) > TAU+EPS:
        raise ValueError('Invalid circular arc')
    if not all(math.isfinite(v) for v in (*p0, *p1, *c, r, start, sweep)):
        raise ValueError('Nonfinite geometry')
    prim = _Primitive(kind, p0, p1, c, r, start, sweep, abs(sweep)*r)
    if _distance(prim.point(0), p0) > 1e-6 or _distance(prim.point(1), p1) > 1e-6:
        raise ValueError('Arc endpoint disagrees with center/radius/angle')
    points = [p0, p1]
    for a in (0., math.pi/2, math.pi, 3*math.pi/2):
        if prim.contains_angle(a):
            points.append((c[0]+r*math.cos(a), c[1]+r*math.sin(a)))
    bounds = (min(x[0] for x in points), min(x[1] for x in points),
              max(x[0] for x in points), max(x[1] for x in points))
    return _Primitive(kind, p0, p1, c, r, start, sweep, abs(sweep)*r, bounds)


def _bbox_distance(a, b):
    dx = max(a[0]-b[2], b[0]-a[2], 0.)
    dy = max(a[1]-b[3], b[1]-a[3], 0.)
    return math.hypot(dx, dy)


def _angle_intervals(p):
    if abs(p.sweep) >= TAU-EPS:
        return [(0., TAU)]
    lo = (p.start if p.sweep > 0 else p.start+p.sweep) % TAU
    hi = lo+abs(p.sweep)
    return [(lo, hi)] if hi <= TAU else [(lo, TAU), (0., hi-TAU)]


def _intersections(a, b):
    """Return exact intersection coordinates and positive-length overlap flag."""
    if _bbox_distance(a.bounds, b.bounds) > EPS:
        return [], False
    if a.kind == 'arc' and b.kind == 'line':
        return _intersections(b, a)
    points = []
    if a.kind == b.kind == 'line':
        u, v, w = _sub(a.p1,a.p0), _sub(b.p1,b.p0), _sub(b.p0,a.p0)
        den = _cross(u,v)
        if abs(den) > 1e-12*a.length*b.length:
            t, q = _cross(w,v)/den, _cross(w,u)/den
            if -EPS <= t <= 1+EPS and -EPS <= q <= 1+EPS:
                points.append(a.point(max(0.,min(1.,t))))
        elif abs(_cross(w,u)) <= EPS*a.length:
            s0, s1 = _dot(w,u)/(a.length*a.length), _dot(_sub(b.p1,a.p0),u)/(a.length*a.length)
            lo, hi = max(0.,min(s0,s1)), min(1.,max(s0,s1))
            if (hi-lo)*a.length > EPS:
                return [], True
            if hi >= lo-EPS:
                points.append(a.point((lo+hi)/2))
    elif a.kind == 'line':
        # Unit-direction projection avoids cancellation of two O(length^4)
        # quadratic terms at a long-line/circle tangency. Tolerance now has
        # units of mm^2 and scales with the circle, not the line length.
        v = ((a.p1[0]-a.p0[0])/a.length,(a.p1[1]-a.p0[1])/a.length)
        w = _sub(a.p0,b.center)
        along,perp = -_dot(w,v),_cross(w,v)
        height2 = b.radius*b.radius-perp*perp
        tol = 1e-12*max(b.radius*b.radius,1.)
        if height2 >= -tol:
            root = 0. if abs(height2)<=tol else math.sqrt(height2)
            for t in ((along-root)/a.length, (along+root)/a.length):
                if -EPS <= t <= 1+EPS:
                    pt = a.point(max(0.,min(1.,t)))
                    if b.contains_angle(math.atan2(pt[1]-b.center[1],pt[0]-b.center[0])):
                        points.append(pt)
    else:
        d = _distance(a.center,b.center)
        if d <= EPS and abs(a.radius-b.radius) <= EPS:
            for lo,hi in _angle_intervals(a):
                for otherlo,otherhi in _angle_intervals(b):
                    if min(hi,otherhi)-max(lo,otherlo) > EPS/max(a.radius,1.):
                        return [], True
            for pt in (a.p0,a.p1,b.p0,b.p1):
                aa = math.atan2(pt[1]-a.center[1],pt[0]-a.center[0])
                if a.contains_angle(aa) and b.contains_angle(aa):
                    points.append(pt)
        elif d > EPS and d <= a.radius+b.radius+EPS and d >= abs(a.radius-b.radius)-EPS:
            u = ((b.center[0]-a.center[0])/d,(b.center[1]-a.center[1])/d)
            x = (a.radius*a.radius-b.radius*b.radius+d*d)/(2*d)
            h = math.sqrt(max(0.,a.radius*a.radius-x*x))
            for sign in (-1,1):
                pt = (a.center[0]+x*u[0]-sign*h*u[1],a.center[1]+x*u[1]+sign*h*u[0])
                if a.contains_angle(math.atan2(pt[1]-a.center[1],pt[0]-a.center[0])) and b.contains_angle(math.atan2(pt[1]-b.center[1],pt[0]-b.center[0])):
                    points.append(pt)
    unique = []
    for pt in points:
        if not any(_distance(pt,old) <= 1e-7 for old in unique):
            unique.append(pt)
    return unique, False


def _point_distance(pt, p):
    if p.kind == 'line':
        return _distance(pt,p.point(p.parameter(pt)))
    a = math.atan2(pt[1]-p.center[1],pt[0]-p.center[0])
    if p.contains_angle(a):
        return abs(_distance(pt,p.center)-p.radius)
    return min(_distance(pt,p.p0),_distance(pt,p.p1))


def _exact_distance(a, b):
    """Exact minimum of finite straight/circular centerline pieces."""
    points, overlap = _intersections(a,b)
    if points or overlap:
        return 0.
    best = min(_point_distance(a.p0,b),_point_distance(a.p1,b),
               _point_distance(b.p0,a),_point_distance(b.p1,a))
    if a.kind == b.kind == 'line':
        return best
    if a.kind == 'arc' and b.kind == 'line':
        a,b = b,a
    if a.kind == 'line':
        u = ((a.p1[0]-a.p0[0])/a.length,(a.p1[1]-a.p0[1])/a.length)
        for sign in (-1,1):
            pt = (b.center[0]-sign*b.radius*u[1],b.center[1]+sign*b.radius*u[0])
            angle = math.atan2(pt[1]-b.center[1],pt[0]-b.center[0])
            raw_t = _dot(_sub(pt,a.p0),u)/a.length
            if b.contains_angle(angle) and 0 <= raw_t <= 1:
                best = min(best,_point_distance(pt,a))
    else:
        d = _distance(a.center,b.center)
        if d > EPS:
            u = ((b.center[0]-a.center[0])/d,(b.center[1]-a.center[1])/d)
            for signa in (-1,1):
                pt = (a.center[0]+signa*a.radius*u[0],a.center[1]+signa*a.radius*u[1])
                if not a.contains_angle(math.atan2(pt[1]-a.center[1],pt[0]-a.center[0])):
                    continue
                for signb in (-1,1):
                    qt = (b.center[0]+signb*b.radius*u[0],b.center[1]+signb*b.radius*u[1])
                    if b.contains_angle(math.atan2(qt[1]-b.center[1],qt[0]-b.center[0])):
                        best = min(best,_distance(pt,qt))
        elif any(min(hi,bhi)-max(lo,blo) >= -EPS for lo,hi in _angle_intervals(a) for blo,bhi in _angle_intervals(b)):
            best = min(best,abs(a.radius-b.radius))
    return best


@dataclass
class PreparedRoute:
    primitives: tuple
    offsets: tuple
    geometry: Any
    length: float
    sagitta: float
    exact_bounds: tuple
    self_intersections: int = 0
    self_overlaps: int = 0
    self_spacing_violations: int = 0
    discontinuities: int = 0

    @property
    def bounds(self):
        return self.exact_bounds


def _kept_primitives(route, intervals):
    if not intervals:
        return route.primitives
    intervals = sorted((max(0.,a),min(route.length,b)) for a,b in intervals)
    merged = []
    for lo,hi in intervals:
        if merged and lo <= merged[-1][1]+EPS:
            merged[-1] = merged[-1][0],max(hi,merged[-1][1])
        else:
            merged.append((lo,hi))
    kept = []
    for primitive,start in zip(route.primitives,route.offsets):
        pieces = [(start,start+primitive.length)]
        for lo,hi in merged:
            next_pieces = []
            for a,b in pieces:
                if hi <= a or lo >= b:
                    next_pieces.append((a,b))
                else:
                    if lo > a+EPS:
                        next_pieces.append((a,lo))
                    if hi < b-EPS:
                        next_pieces.append((hi,b))
            pieces = next_pieces
        kept.extend(primitive.clip((a-start)/primitive.length,(b-start)/primitive.length)
                    for a,b in pieces if b-a > EPS)
    return tuple(kept)


def _pieces_too_close(left, right, required):
    for a in left:
        for b in right:
            if _bbox_distance(a.bounds,b.bounds) >= required-EPS:
                continue
            distance = _exact_distance(a,b)
            if distance < required-EPS:
                return True,distance
    return False,None


class ConflictIndex:
    """All rows share this index. No layer partition is supported.

    ``evaluate`` defaults to stopping at its first illegal pair for search.
    Use ``stop_on_invalid=False`` for final pairwise auditing. ``prepare`` can
    be shared by repeated strategy runs; ``add`` also accepts prepared routes.
    The crossing-window length is centerline clearance / sin(crossing angle)
    plus a 2*sagitta numerical margin, applied along each exact curve. Closely
    spaced repeated crossings whose local windows overlap are conservatively
    rejected rather than excusing a long segment of a near-coincident route.
    """
    def __init__(self, width=.05, gap=.125, sagitta=.0005, cache_size=4096):
        self.width,self.gap,self.sagitta = float(width),float(gap),float(sagitta)
        if self.width <= 0 or self.gap < 0 or self.sagitta <= 0:
            raise ValueError('Positive width and sagitta, nonnegative gap required')
        self.clearance = self.width+self.gap
        self.routes = {}
        self._tree = None
        self._tree_ids = []
        self._tree_bounds = np.empty((0,4))
        self._pending = set()
        self._removed = set()
        self._cache = OrderedDict()
        self._cache_size = cache_size

    def __len__(self):
        return len(self.routes)

    def prepare(self, primitives):
        if isinstance(primitives,PreparedRoute):
            return primitives
        primitives = tuple(primitives)
        key = tuple((p['kind'],tuple(p['p0']),tuple(p['p1']),tuple(p.get('center',())),
                     p.get('radius'),p.get('start_angle'),p.get('sweep'),p.get('layer',0),p.get('z',0))
                    for p in primitives)
        if key in self._cache:
            result = self._cache.pop(key)
            self._cache[key] = result
            return result
        ps = tuple(_make_primitive(p) for p in primitives)
        if not ps:
            raise ValueError('Empty route')
        coords,offsets,offset = [],[],0.
        discontinuities = 0
        for i,p in enumerate(ps):
            offsets.append(offset)
            offset += p.length
            if i and _distance(ps[i-1].p1,p.p0) > 1e-6:
                discontinuities += 1
            if p.kind == 'line':
                points = [p.p0,p.p1]
            else:
                step = 2*math.acos(max(-1.,min(1.,1-self.sagitta/p.radius)))
                count = max(1,math.ceil(abs(p.sweep)/step))
                points = [p.point(j/count) for j in range(count+1)]
            coords.extend(points if not coords else points[1:])
        intersections,overlaps,self_spacing = 0,0,0
        for i,a in enumerate(ps):
            for j in range(i+1,len(ps)):
                b = ps[j]
                points,overlap = _intersections(a,b)
                overlaps += int(overlap)
                intersections += sum(not (j == i+1 and _distance(pt,a.p1)<1e-6 and _distance(pt,b.p0)<1e-6) for pt in points)
                if j > i+1 and offsets[j]-(offsets[i]+a.length) > 2*self.clearance:
                    if _bbox_distance(a.bounds,b.bounds) < self.clearance-EPS and _exact_distance(a,b) < self.clearance-EPS:
                        self_spacing += 1
        exact_bounds = (min(p.bounds[0] for p in ps),min(p.bounds[1] for p in ps),
                        max(p.bounds[2] for p in ps),max(p.bounds[3] for p in ps))
        result = PreparedRoute(ps,tuple(offsets),LineString(coords) if HAS_SHAPELY else None,offset,
                               self.sagitta if any(p.kind=='arc' for p in ps) else 0.,
                               exact_bounds,
                               intersections,overlaps,self_spacing,discontinuities)
        self._cache[key] = result
        while len(self._cache)>self._cache_size:
            self._cache.popitem(last=False)
        return result

    def add(self, route_id, primitives):
        if route_id in self.routes:
            self.remove(route_id)
        self.routes[route_id] = self.prepare(primitives)
        self._pending.add(route_id)

    def remove(self, route_id):
        self.routes.pop(route_id,None)
        self._pending.discard(route_id)
        self._removed.add(route_id)

    def _nearby(self, route):
        if self._tree is None or len(self._pending)+len(self._removed)>=16:
            self._tree_ids = list(self.routes)
            self._tree_bounds = np.array([self.routes[i].bounds for i in self._tree_ids],dtype=float).reshape((-1,4))
            self._tree = STRtree([self.routes[i].geometry for i in self._tree_ids]) if HAS_SHAPELY else True
            self._pending.clear()
            self._removed.clear()
        if not self.routes:
            return []
        # Each chord deviates at most sagitta from its exact arc. Include both
        # errors in the broad phase; exact predicates make the final decision.
        if HAS_SHAPELY:
            indices = self._tree.query(route.geometry,predicate='dwithin',
                                       distance=self.clearance+2*self.sagitta)
        else:
            # Exact analytic extrema, including arc quadrant extrema. Inflate
            # the candidate box by clearance+2*sagitta and use a NumPy broad
            # phase. This may include extra pairs but cannot miss a collision.
            boxes = self._tree_bounds
            x0,y0,x1,y1 = route.bounds
            pad = self.clearance+2*self.sagitta
            indices = np.flatnonzero((boxes[:,0]<=x1+pad)&(boxes[:,2]>=x0-pad)&
                                     (boxes[:,1]<=y1+pad)&(boxes[:,3]>=y0-pad))
        ids = {self._tree_ids[int(i)] for i in indices}
        ids.difference_update(self._removed)
        for i in self._pending:
            near = (route.geometry.distance(self.routes[i].geometry) if HAS_SHAPELY
                    else _bbox_distance(route.bounds,self.routes[i].bounds))
            if near <= self.clearance+2*self.sagitta:
                ids.add(i)
        return sorted(ids,key=lambda i: str(i))

    def evaluate(self, primitives, exclude=None, stop_on_invalid=True):
        route = self.prepare(primitives)
        excluded = set() if exclude is None else (set(exclude) if isinstance(exclude,(list,tuple,set)) else {exclude})
        result = dict(valid=True,spacing_pairs=[],overlap_pairs=[],touch_pairs=[],
            crossing_zone_overlap_pairs=[],self_intersections=route.self_intersections,
            self_overlaps=route.self_overlaps,self_spacing_violations=route.self_spacing_violations,
            discontinuities=route.discontinuities,crossings=[],minimum_non_crossing_centerline_mm=None,
            checked_pairs=0,clearance_mm=self.clearance,layer=0)
        if route.self_intersections or route.self_overlaps or route.self_spacing_violations or route.discontinuities:
            result['valid'] = False
            if stop_on_invalid:
                return result
        for other_id in self._nearby(route):
            if other_id in excluded or other_id not in self.routes:
                continue
            other = self.routes[other_id]
            result['checked_pairs'] += 1
            crossings,overlap,touch = [],False,False
            for i,a in enumerate(route.primitives):
                for j,b in enumerate(other.primitives):
                    points,common = _intersections(a,b)
                    overlap |= common
                    for pt in points:
                        ta,tb = a.parameter(pt),b.parameter(pt)
                        tangent_a,tangent_b = a.tangent(ta),b.tangent(tb)
                        sine = min(1.,abs(_cross(tangent_a,tangent_b)))
                        sa,sb = route.offsets[i]+ta*a.length,other.offsets[j]+tb*b.length
                        is_endpoint = min(sa,route.length-sa,sb,other.length-sb) < 1e-7
                        if sine < 1e-7 or is_endpoint:
                            touch = True
                            continue
                        if not any(_distance(pt,c['point'])<1e-6 for c in crossings):
                            crossings.append(dict(point=pt,sa=sa,sb=sb,sine=sine,
                                                  angle_deg=math.degrees(math.asin(sine))))
            if overlap:
                result['overlap_pairs'].append(other_id)
            if touch:
                result['touch_pairs'].append(other_id)
            ia,ib = [],[]
            for c in crossings:
                half = self.clearance/c['sine']+2*self.sagitta
                ia.append((c['sa']-half,c['sa']+half))
                ib.append((c['sb']-half,c['sb']+half))
                result['crossings'].append(dict(other=other_id,x=c['point'][0],y=c['point'][1],
                    angle_deg=c['angle_deg'],local_exemption_half_length_mm=half))
            zone_overlap = any(x[1]>y[0]+EPS for intervals in (ia,ib)
                               for x,y in zip(sorted(intervals),sorted(intervals)[1:]))
            if zone_overlap:
                result['crossing_zone_overlap_pairs'].append(other_id)
            if (overlap or touch or zone_overlap) and stop_on_invalid:
                result['valid'] = False
                return result
            # Check outside-A against ALL of B and outside-B against ALL of A.
            # Cutting both first would wrongly excuse outside/inside near misses.
            outside_a,outside_b = _kept_primitives(route,ia),_kept_primitives(other,ib)
            bad,distance = _pieces_too_close(outside_a,other.primitives,self.clearance)
            if not bad and crossings:
                bad,distance = _pieces_too_close(outside_b,route.primitives,self.clearance)
            if bad:
                result['spacing_pairs'].append(other_id)
                old = result['minimum_non_crossing_centerline_mm']
                result['minimum_non_crossing_centerline_mm'] = distance if old is None else min(old,distance)
            if overlap or touch or zone_overlap or bad:
                result['valid'] = False
                if stop_on_invalid:
                    return result
        return result
