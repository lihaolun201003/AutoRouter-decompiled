"""Experimental two-layer, single-route elevation probe. No allocator edits."""
from dataclasses import dataclass, asdict
from copy import deepcopy
from math import isfinite
from .models import Layer, Point3D
from .geometry_3d import (LineSegment3D, PlanarArcSegment3D, CosineTransition3D,
    PathWindowTransition3D, Route3D)
from .geometry_3d_diagnostics import minimum_xy_run_for_radius, analyze_route3d_joins
from .clearance_3d import analyze_route3d_clearance, analyze_route3d_self_clearance, _parameter_xy


@dataclass(frozen=True)
class LayerConfiguration:
    layers: tuple
    clearance_mm: float
    required_radius_mm: float
    transition_policy: str
    parameter_status: str

    def __post_init__(self):
        object.__setattr__(self, 'layers', tuple(deepcopy(self.layers)))
        self.validate()

    def validate(self):
        if len(self.layers) != 2 or any(type(x) is not Layer for x in self.layers):
            raise ValueError('EXACTLY_TWO_LAYERS_REQUIRED')
        for layer in self.layers: layer.validate()
        if len({x.layer_id for x in self.layers}) != 2: raise ValueError('DUPLICATE_LAYER_ID')
        if len({x.z_mm for x in self.layers}) != 2: raise ValueError('DUPLICATE_LAYER_Z')
        if self.layers[0].layer_id != 0 or self.layers[1].layer_id != 1 or self.layers[0].z_mm != 0 or self.layers[1].z_mm <= 0:
            raise ValueError('REQUIRE_LAYER_0_AT_ZERO_AND_LAYER_1')
        if not all(type(x) in (int,float) and isfinite(x) and x > 0 for x in (self.clearance_mm, self.required_radius_mm)):
            raise ValueError('POSITIVE_EXPLICIT_CLEARANCE_AND_RADIUS_REQUIRED')
        if self.transition_policy != 'LINE_ONLY_FINITE_WINDOWS': raise ValueError('UNSUPPORTED_TRANSITION_POLICY')
        if self.parameter_status != 'EXPERIMENTAL_SYNTHETIC': raise ValueError('EXPERIMENTAL_PARAMETERS_REQUIRED')


@dataclass(frozen=True)
class ElevationCandidate3D:
    route_id: int
    target_pair: tuple
    target_crossing: tuple
    layer_from: int
    layer_to: int
    rise_start: Point3D
    rise_end: Point3D
    elevated_start: Point3D
    elevated_end: Point3D
    fall_start: Point3D
    fall_end: Point3D
    transition_run_mm: float
    delta_z: float
    required_radius_mm: float
    minimum_radius_mm: float
    rise_window: tuple
    fall_window: tuple
    original_length_mm: float
    new_length_mm: float
    extra_length_mm: float
    elevated_length_mm: float
    route: Route3D

    @property
    def window_kind(self):
        return 'LINE_WINDOW_G0'

    @property
    def rise_span(self):
        """Canonical 4-tuple (start primitive, start t, end primitive, end t).

        A single-primitive line window has start primitive == end primitive, so
        old and new windows are directly comparable when they are sorted or
        grouped together."""
        if not self.rise_window:
            return ()
        i,u,v=self.rise_window
        return (i,u,i,v)

    @property
    def fall_span(self):
        if not self.fall_window:
            return ()
        j,x,y=self.fall_window
        return (j,x,j,y)


def _at_z(p, z): return Point3D(p.x, p.y, z)


def _raised(p, z):
    if isinstance(p, LineSegment3D): return LineSegment3D(_at_z(p.start,z), _at_z(p.end,z))
    q=deepcopy(p)
    object.__setattr__(q, 'z', z)
    q.validate()
    return q


def _locations(route, crossings, tol=1e-7):
    locations=[]
    for point in crossings:
        matches=[]
        for i,p in enumerate(route.primitives):
            t=_parameter_xy(p,point.x,point.y,tol)
            if t is not None and p.point_at(t).distance_to(_at_z(point,0)) <= tol: matches.append((i,t))
        if not matches: raise ValueError('TARGET_CROSSING_NOT_ON_ROUTE')
        locations.extend(matches)
    if not locations: raise ValueError('TARGET_CROSSING_REQUIRED')
    return min(locations),max(locations)


def build_elevation_candidate(route, target_pair, crossings, config, rise_window, fall_window, *, target_layer_id=1):
    """Windows are (primitive index, start parameter, end parameter); never cut arcs."""
    config.validate(); route.validate()
    if not route.primitives or any(not isinstance(p,(LineSegment3D,PlanarArcSegment3D)) or
            p.start.z != 0 or p.end.z != 0 for p in route.primitives):
        raise ValueError('REQUIRE_PLANAR_LAYER_ZERO_ROUTE')
    i,u,v=rise_window; j,x,y=fall_window
    if not (0 <= i <= j < len(route.primitives) and 0 <= u < v <= 1 and 0 <= x < y <= 1):
        raise ValueError('INVALID_WINDOW')
    if not isinstance(route.primitives[i],LineSegment3D) or not isinstance(route.primitives[j],LineSegment3D):
        raise ValueError('NO_VALID_TRANSITION_WINDOW')
    if i == j and v >= x: raise ValueError('OVERLAPPING_WINDOWS')
    first,last=_locations(route,crossings)
    if not ((i,v) < first and last < (j,x)): raise ValueError('TARGET_NOT_COVERED')
    targets=[layer for layer in config.layers[1:] if layer.layer_id==target_layer_id]
    if len(targets)!=1: raise ValueError('INVALID_TARGET_LAYER')
    height=targets[0].z_mm
    a,b=route.primitives[i],route.primitives[j]
    up=CosineTransition3D(a.point_at(u),_at_z(a.point_at(v),height))
    down=CosineTransition3D(_at_z(b.point_at(x),height),b.point_at(y))
    required=minimum_xy_run_for_radius(height,config.required_radius_mm)
    if min(up.lxy,down.lxy) < required: raise ValueError('INSUFFICIENT_TRANSITION_SPACE')
    pieces=[]
    def linepart(p,s,t,z):
        if t>s: pieces.append(LineSegment3D(_at_z(p.point_at(s),z),_at_z(p.point_at(t),z)))
    for k,p in enumerate(route.primitives):
        if k<i or k>j: pieces.append(deepcopy(p))
        elif i==j:
            linepart(p,0,u,0);pieces.append(up);linepart(p,v,x,height);pieces.append(down);linepart(p,y,1,0)
        elif k==i:
            linepart(p,0,u,0);pieces.append(up);linepart(p,v,1,height)
        elif k==j:
            linepart(p,0,x,height);pieces.append(down);linepart(p,y,1,0)
        else: pieces.append(_raised(p,height))
    elevated=Route3D(route.route_id,pieces)
    before,after=route.total_length(),elevated.total_length()
    high=sum(p.length() for p in pieces if isinstance(p,(LineSegment3D,PlanarArcSegment3D)) and p.start.z==height)
    return ElevationCandidate3D(route.route_id,tuple(target_pair),tuple(deepcopy(crossings)),0,target_layer_id,
        up.start,up.end,up.end,down.start,down.start,down.end,min(up.lxy,down.lxy),height,
        config.required_radius_mm,min(up.minimum_curvature_radius(),down.minimum_curvature_radius()),
        tuple(rise_window),tuple(fall_window),before,after,after-before,high,elevated)


def elevation_candidates(route,target_pair,crossings,config,*,target_layer_id=1,window_slack_mm=0.0):
    """Three stable placements per legal before/after straight interval; finite search.

    window_slack_mm: strictly positive placement margin (mm) added to the
    clearance-derived endpoint pad. With pad==clearance the generator can put a
    non-adjacent primitive exactly on the 0.1 mm threshold, where the
    conservative distance bounds straddle the threshold and the candidate can
    never be certified CLEAR. A slack of 1e-5 mm is >=10x the worst converged
    ADAPTIVE_CHORD_BOUNDS error bound (distance_tol=1e-6 mm) and 1e4x the
    analytic classification tol (1e-9 mm), while shifting a ~5 mm window by
    3e-6 of the 300 mm board. The clearance criterion itself stays 0.1 mm.
    Default 0.0 reproduces the historical behaviour exactly."""
    config.validate(); route.validate()
    if type(window_slack_mm) not in (int,float) or not isfinite(window_slack_mm) or window_slack_mm<0:
        raise ValueError('WINDOW_SLACK_MUST_BE_FINITE_AND_NONNEGATIVE')
    if any(not isinstance(p,(LineSegment3D,PlanarArcSegment3D)) or p.start.z!=0 or p.end.z!=0 for p in route.primitives):
        raise ValueError('REQUIRE_PLANAR_LAYER_ZERO_ROUTE')
    first,last=_locations(route,crossings)
    # Tiny geometric slack prevents rounding below the required true radius.
    targets=[layer for layer in config.layers[1:] if layer.layer_id==target_layer_id]
    if len(targets)!=1: raise ValueError('INVALID_TARGET_LAYER')
    run=minimum_xy_run_for_radius(targets[0].z_mm,config.required_radius_mm)*(1+1e-9)
    rises=[];falls=[];has_before=False;has_after=False
    for i,p in enumerate(route.primitives):
        if not isinstance(p,LineSegment3D): continue
        length=p.length(); pad=(max(1e-7,config.clearance_mm)+window_slack_mm)/length
        for collection,lo,hi in ((rises,pad,first[1]-pad if i==first[0] else 1-pad if i<first[0] else -1),
                                  (falls,last[1]+pad if i==last[0] else pad if i>last[0] else 2,1-pad)):
            if hi>lo:
                if collection is rises: has_before=True
                else: has_after=True
            width=run/length
            if hi-lo<width: continue
            for fraction in (0.,.5,1.):
                start=lo+fraction*(hi-lo-width)
                window=(i,start,start+width)
                if window not in collection: collection.append(window)
    if not has_before or not has_after: return [],'NO_VALID_TRANSITION_WINDOW'
    if not rises or not falls: return [],'INSUFFICIENT_TRANSITION_SPACE'
    results=[]
    for rise in rises:
        for fall in falls:
            results.append(build_elevation_candidate(route,target_pair,crossings,config,rise,fall,target_layer_id=target_layer_id))
    return results,None


def evaluate_elevation(candidate,original,other,config):
    config.validate()
    c=candidate; r=c.route; r.validate()
    joins=analyze_route3d_joins(r)
    self_result=analyze_route3d_self_clearance(r,config.clearance_mm)
    target=analyze_route3d_clearance(r,other,config.clearance_mm)
    before=analyze_route3d_clearance(original,other,config.clearance_mm)
    endpoints=r.start_point==original.start_point and r.end_point==original.end_point
    index=[k for k,p in enumerate(r.primitives)
           if isinstance(p,CosineTransition3D) or type(p) is PathWindowTransition3D]
    radius=min((r.primitives[k].minimum_curvature_radius() for k in index),default=float('inf'))
    joining=None
    if any(type(r.primitives[k]) is PathWindowTransition3D for k in index):
        # Certify the WHOLE window and BOTH joining sides: the window's own
        # exact maximum curvature is in minimum_curvature_radius(), and the
        # primitives it joins to must already satisfy the same radius bound.
        joining=[]
        for k in index:
            for neighbour in (k-1,k+1):
                if not 0<=neighbour<len(r.primitives):
                    continue
                p=r.primitives[neighbour]
                if type(p) is PlanarArcSegment3D:
                    joining.append(dict(primitive_index=neighbour,radius_mm=p.radius,
                                        passes=bool(p.radius>=config.required_radius_mm)))
                else:
                    joining.append(dict(primitive_index=neighbour,radius_mm=float('inf'),passes=True))
    reasons=[]
    if not endpoints: reasons.append('ENDPOINT_CHANGED')
    if not joins.all_C0 or not joins.all_C1_direction: reasons.append('JOIN_FAILED')
    if radius<config.required_radius_mm: reasons.append('RADIUS_FAILED')
    if joining is not None and not all(row['passes'] for row in joining):
        reasons.append('JOINING_SIDE_RADIUS_FAILED')
    if self_result['status']!='CLEAR': reasons.append('SELF_COLLISION' if self_result['status']=='COLLISION' else 'SELF_'+self_result['status'])
    if before['status']!='COLLISION': reasons.append('BASELINE_TARGET_NOT_COLLIDING')
    if target['status']!='CLEAR': reasons.append('TARGET_NOT_CLEARED')
    return dict(status='ACCEPTED_TARGET_PAIR_ONLY' if not reasons else 'REJECTED',reasons=reasons,
        endpoint_invariant=endpoints,joins=asdict(joins),minimum_radius_mm=radius,
        joining_side_certificate=joining,
        self_clearance=self_result,target_before=before,target_after=target,
        target_collision_removed=before['status']=='COLLISION' and target['status']=='CLEAR',
        local_validation_status='NOT_PERFORMED',new_collisions_created=None,old_collisions_removed=None)


def probe_single_route_elevation(route,other,crossings,config):
    frozen=deepcopy((route,other,config))
    candidates,failure=elevation_candidates(route,(route.route_id,other.route_id),crossings,config)
    rows=[]
    for c in candidates:
        evaluation=evaluate_elevation(c,route,other,config)
        # Neighbor collision count is UNKNOWN, not zero. Equal unknown field
        # cannot distinguish candidates; then use transition count/lengths/windows.
        rank=(not evaluation['target_collision_removed'],2,c.extra_length_mm,c.elevated_length_mm,c.rise_window,c.fall_window)
        rows.append(dict(candidate=c,evaluation=evaluation,rank=rank))
    rows.sort(key=lambda r:r['rank'])
    accepted=[r for r in rows if r['evaluation']['status']=='ACCEPTED_TARGET_PAIR_ONLY']
    assert (route,other,config)==frozen
    return dict(status='ACCEPTED_TARGET_PAIR_ONLY' if accepted else failure or 'NO_ACCEPTED_CANDIDATE',
        candidate_count=len(rows),accepted_count=len(accepted),selected=accepted[0] if accepted else None,
        candidates=rows,baseline_unchanged=True,local_validation_status='NOT_PERFORMED')
