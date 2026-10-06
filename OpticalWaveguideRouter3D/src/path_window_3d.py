"""v8: path-arc-length elevation windows on the FROZEN planar route.

G0 (LINE_ONLY) is untouched: this module only ADDS candidates. Every window
here is a contiguous planar ARC-LENGTH interval of the frozen z=0 route, so it
may cut arcs and cross primitive boundaries while the XY locus stays exactly on
the frozen path (sub-curves are analytic, never chords). The rise and the fall
are each ONE shared cosine phase (PathWindowTransition3D), never restarted per
piece.

Frozen enumeration (declared before any formal evaluation):
  placements  PATH_WINDOW_PLACEMENTS = (0.0, 0.5, 1.0) of the free interval
  lengths     PATH_WINDOW_LENGTH_FACTORS = (1.0, 1.5, 2.0, 3.0) x L0, where
              L0 = minimum_xy_run_for_radius(delta_z, required_radius)
  cap         PATH_WINDOW_CANDIDATE_CAP candidates per victim; truncation is
              counted, never silent

The required planar run grows with the planar curvature the window covers:
with K = sqrt(1/R^2 - kappa_xy_max^2) the exact maximum curvature of a path
window is sqrt(kappa_xy_max^2 + (pi^2|dz|/(2L^2))^2), so L >= pi*sqrt(|dz|/(2K)).
If kappa_xy_max >= 1/R no legal length exists and the window is REJECTED
(conservative: the radius requirement is never relaxed and XY never changes).
"""
from dataclasses import dataclass
from math import isfinite, sqrt, pi
from .models import Point3D
from .geometry_3d import (LineSegment3D, PlanarArcSegment3D, PathWindowTransition3D,
    Route3D, planar_sub_curve, _finite)
from .geometry_3d_diagnostics import minimum_xy_run_for_radius
from .clearance_3d import _parameter_xy

PATH_WINDOW_PLACEMENTS=(0.0,0.5,1.0)
PATH_WINDOW_LENGTH_FACTORS=(1.0,1.5,2.0,3.0)
PATH_WINDOW_CANDIDATE_CAP=4096
# A sub-interval end this close to a primitive boundary is snapped to the
# boundary itself: one ulp away the interpolated endpoint differs from the
# frozen endpoint by ~1e-14 mm and the exact endpoint invariant would fail.
BOUNDARY_SNAP_MM=1e-9
WINDOW_KIND_LINE='LINE_WINDOW_G0'
WINDOW_KIND_PATH='PATH_WINDOW_G1'


def planar_path_model(route):
    """Frozen planar (z=0) path model: primitives, lengths, cumulative offsets."""
    route.validate()
    prims=list(route.primitives)
    if not prims or any(type(p) not in (LineSegment3D,PlanarArcSegment3D)
                        or p.start.z!=0. or p.end.z!=0. for p in prims):
        raise ValueError('REQUIRE_PLANAR_LAYER_ZERO_ROUTE')
    lengths=[p.length() for p in prims]
    offsets=[];run=0.
    for length in lengths:
        offsets.append(run);run+=length
    _finite(run)
    if run<=0:
        raise ValueError('PLANAR_ROUTE_HAS_NO_LENGTH')
    return dict(primitives=prims,lengths=lengths,offsets=offsets,total=run)


def path_offsets_of_point(model,point,tol=1e-7):
    """Every planar arc-length offset on the frozen path whose XY equals point."""
    _finite(tol)
    found=[]
    for k,p in enumerate(model['primitives']):
        t=_parameter_xy(p,point.x,point.y,tol)
        if t is None:
            continue
        q=p.point_at(t)
        if q.distance_to(Point3D(point.x,point.y,q.z))<=tol:
            value=model['offsets'][k]+t*model['lengths'][k]
            if value not in found:
                found.append(value)
    return found


def offset_of_primitive_parameter(model,k,t):
    _finite(t)
    if not 0<=t<=1 or not 0<=k<len(model['primitives']):
        raise ValueError('INVALID_PRIMITIVE_PARAMETER')
    return model['offsets'][k]+t*model['lengths'][k]


def split_path_interval(model,a,b):
    """[(primitive index, start parameter, end parameter)] covering [a,b]."""
    _finite(a,b)
    if not 0<=a<b<=model['total']:
        raise ValueError('INTERVAL_OUTSIDE_THE_FROZEN_PATH')
    rows=[]
    for k,length in enumerate(model['lengths']):
        lo=model['offsets'][k];hi=lo+length
        if b<=lo or a>=hi:
            continue
        s=max(a,lo);t=min(b,hi)
        if t>s:
            u=(s-lo)/length;v=(t-lo)/length
            if (s-lo)<=BOUNDARY_SNAP_MM:u=0.
            if (hi-t)<=BOUNDARY_SNAP_MM:v=1.
            u=0. if u<0. else (1. if u>1. else u)
            v=0. if v<0. else (1. if v>1. else v)
            # A sub-curve shorter than 1e-12 mm is a rounding sliver next to a
            # primitive boundary, not geometry: dropping it keeps the XY path
            # continuous to within 1e-12 mm, far below the 1e-9 mm route
            # continuity tolerance, and avoids a zero-length piece.
            if v>u and (v-u)*length>1e-12:
                rows.append((k,u,v))
    return rows


def minimum_path_run_for_curvature(delta_z,required_radius,kappa_xy_max):
    """(L_min, feasible): exact minimum planar run of a window whose worst
    planar curvature is kappa_xy_max. L_min = pi*sqrt(|dz|/(2K)) with
    K = sqrt(1/R^2 - kappa_xy_max^2); infeasible when kappa_xy_max >= 1/R."""
    _finite(delta_z,required_radius,kappa_xy_max)
    if required_radius<=0 or delta_z==0:
        raise ValueError('TRANSITION_REQUIRES_A_POSITIVE_RADIUS_AND_A_HEIGHT_CHANGE')
    if kappa_xy_max<0:
        raise ValueError('CURVATURE_MUST_BE_NONNEGATIVE')
    target=1./required_radius
    if kappa_xy_max>=target:
        return None,False
    K=sqrt(target*target-kappa_xy_max*kappa_xy_max)
    if K<=0:
        return None,False
    value=pi*sqrt(abs(delta_z)/(2.*K))
    _finite(value)
    return value,True


@dataclass(frozen=True)
class PathWindowCandidate3D:
    """A rise/fall pair whose windows follow the frozen planar path.

    Field names mirror ElevationCandidate3D so the shared engine ranking, cost
    accounting and ledger work unchanged; window_kind and the certificates are
    additional. rise_span/fall_span are the canonical 4-tuples
    (start primitive, start parameter, end primitive, end parameter) that make
    old and new windows type-compatible when they are sorted together.
    """
    route_id: int
    target_pair: tuple
    target_crossing: tuple
    layer_from: int
    layer_to: int
    rise_span: tuple
    fall_span: tuple
    rise_offsets_mm: tuple
    fall_offsets_mm: tuple
    transition_run_mm: float
    delta_z: float
    required_radius_mm: float
    minimum_radius_mm: float
    rise_curvature_certificate: dict
    fall_curvature_certificate: dict
    original_length_mm: float
    new_length_mm: float
    extra_length_mm: float
    elevated_length_mm: float
    route: Route3D

    @property
    def window_kind(self):
        return WINDOW_KIND_PATH

    @property
    def rise_window(self):
        return self.rise_span

    @property
    def fall_window(self):
        return self.fall_span

    @property
    def rise_piece_count(self):
        return self.rise_curvature_certificate['piece_count']

    @property
    def fall_piece_count(self):
        return self.fall_curvature_certificate['piece_count']


def _target_layer(config,target_layer_id):
    targets=[layer for layer in config.layers[1:] if layer.id==target_layer_id]
    if len(targets)!=1:
        raise ValueError('INVALID_TARGET_LAYER')
    return targets[0]


def build_path_window_candidate(route,target_pair,crossings,config,rise_offsets,fall_offsets,
                                *,target_layer_id=1):
    """Build the elevated route for one (rise, fall) path-window pair."""
    config.validate();route.validate()
    model=planar_path_model(route)
    total=model['total']
    rise_start,rise_end=rise_offsets
    fall_start,fall_end=fall_offsets
    _finite(rise_start,rise_end,fall_start,fall_end)
    if not 0.<=rise_start<rise_end<=fall_start<fall_end<=total:
        raise ValueError('INVALID_PATH_WINDOWS')
    offset_rows=[]
    for point in crossings:
        found=path_offsets_of_point(model,point)
        if not found:
            raise ValueError('TARGET_CROSSING_NOT_ON_ROUTE')
        offset_rows.extend(found)
    if not offset_rows:
        raise ValueError('TARGET_CROSSING_REQUIRED')
    first,last=min(offset_rows),max(offset_rows)
    if not (rise_end<=first and last<=fall_start):
        raise ValueError('TARGET_NOT_COVERED')
    layer=_target_layer(config,target_layer_id)
    height=layer.z_mm
    cuts={0.,total,rise_start,rise_end,fall_start,fall_end}
    cuts.update(model['offsets'])
    ordered=sorted(cuts)
    before=[];rise_pieces=[];middle=[];fall_pieces=[];after=[]
    for x,y in zip(ordered,ordered[1:]):
        if y<=x:
            continue
        mid=(x+y)/2.
        if mid<rise_start:
            bucket,z=before,0.
        elif mid<rise_end:
            bucket,z=rise_pieces,0.
        elif mid<fall_start:
            bucket,z=middle,height
        elif mid<fall_end:
            bucket,z=fall_pieces,0.
        else:
            bucket,z=after,0.
        for k,u,v in split_path_interval(model,x,y):
            bucket.append(planar_sub_curve(model['primitives'][k],u,v,z))
    if not rise_pieces or not fall_pieces:
        raise ValueError('EMPTY_PATH_WINDOW')
    rise=PathWindowTransition3D(tuple(rise_pieces),0.,height)
    fall=PathWindowTransition3D(tuple(fall_pieces),height,0.)
    pieces=before+[rise]+middle+[fall]+after
    elevated=Route3D(route.route_id,tuple(pieces))
    spans=[]
    for offsets,prims in ((rise_offsets,rise_pieces),(fall_offsets,fall_pieces)):
        rows=split_path_interval(model,offsets[0],offsets[1])
        first_row,last_row=rows[0],rows[-1]
        spans.append((first_row[0],first_row[1],last_row[0],last_row[2]))
    try:
        before_length=route.total_length()
        after_length=elevated.total_length()
    except RuntimeError as ex:
        # A non-converged arc-length integral is a REJECTION, never an unchecked
        # estimate and never a crash inside the search loop.
        raise ValueError('PATH_WINDOW_LENGTH_NOT_CONVERGED:'+str(ex))
    high=sum(p.length() for p in pieces
             if p.start.z==height and p.end.z==height)
    _finite(high)
    minimum_radius=min(rise.minimum_curvature_radius(),fall.minimum_curvature_radius())
    return PathWindowCandidate3D(route.route_id,tuple(target_pair),tuple(crossings),0,
        target_layer_id,spans[0],spans[1],tuple(rise_offsets),tuple(fall_offsets),
        min(rise.planar_run_mm,fall.planar_run_mm),height,config.required_radius_mm,
        minimum_radius,rise.curvature_certificate(),fall.curvature_certificate(),
        before_length,after_length,after_length-before_length,high,elevated)


def path_window_candidates(route,target_pair,crossings,config,*,window_slack_mm=0.0,
                           placements=PATH_WINDOW_PLACEMENTS,
                           length_factors=PATH_WINDOW_LENGTH_FACTORS,
                           cap=PATH_WINDOW_CANDIDATE_CAP,target_layer_id=1):
    """Finite, pre-registered path-window enumeration. Returns (candidates, stats).

    Windows are placed inside the legal interval before the FIRST crossing
    (rise) and after the LAST crossing (fall), with the frozen placement
    fractions and the frozen length multiples. The counting is complete:
    no_legal_interval / length_does_not_fit / curvature_rejected /
    build_rejected / cap_truncated are all recorded, and no rejection is ever
    reported as a zero-candidate generation."""
    config.validate();route.validate()
    if type(window_slack_mm) not in (int,float) or not isfinite(window_slack_mm) or window_slack_mm<0:
        raise ValueError('WINDOW_SLACK_MUST_BE_FINITE_AND_NONNEGATIVE')
    if type(cap) is not int or cap<1:
        raise ValueError('CAP_MUST_BE_A_POSITIVE_INTEGER')
    model=planar_path_model(route)
    layer=_target_layer(config,target_layer_id)
    height=layer.z_mm
    offset_rows=[]
    for point in crossings:
        found=path_offsets_of_point(model,point)
        if not found:
            raise ValueError('TARGET_CROSSING_NOT_ON_ROUTE')
        offset_rows.extend(found)
    stats=dict(window_kind=WINDOW_KIND_PATH,target_layer_id=target_layer_id,
               planar_total_length_mm=model['total'],placements=list(placements),
               length_factors=list(length_factors),cap=cap,
               anchor_count=len(offset_rows))
    if not offset_rows:
        raise ValueError('TARGET_CROSSING_REQUIRED')
    first,last=min(offset_rows),max(offset_rows)
    stats['first_crossing_offset_mm']=first
    stats['last_crossing_offset_mm']=last
    pad=max(1e-7,config.clearance_mm)+window_slack_mm
    base_run=minimum_xy_run_for_radius(height,config.required_radius_mm)
    stats['zero_curvature_minimum_run_mm']=base_run
    legal=dict(rise=(0.,first-pad),fall=(last+pad,model['total']))
    stats['legal_interval_mm']={k:[v[0],v[1]] for k,v in legal.items()}
    stats['no_legal_interval']={k:bool(v[1]<=v[0]) for k,v in legal.items()}
    windows=dict(rise=[],fall=[])
    seen_keys=dict(rise=set(),fall=set())
    stats['length_does_not_fit']=dict(rise=0,fall=0)
    for label,(lo,hi) in legal.items():
        if hi<=lo:
            continue
        for factor in length_factors:
            length=base_run*factor
            if length>hi-lo:
                stats['length_does_not_fit'][label]+=1
                continue
            free=(hi-lo)-length
            for fraction in placements:
                start=lo+fraction*free
                end=start+length
                if end>hi:
                    # only ever a rounding excess of the interval end
                    end=hi
                if not end>start:
                    continue
                # dedup on a rounded key, but keep the exact offsets for the
                # construction so a rounding step can never push a window past
                # the end of the frozen path
                key=(round(start,9),round(end,9))
                if key not in seen_keys[label]:
                    seen_keys[label].add(key)
                    windows[label].append((start,end))
    stats['rise_window_count']=len(windows['rise'])
    stats['fall_window_count']=len(windows['fall'])
    stats['curvature_rejected']=0
    stats['build_rejected']=0
    stats['rejection_reasons']={}
    results=[]
    for rise in windows['rise']:
        for fall in windows['fall']:
            if len(results)>=cap:
                break
            try:
                candidate=build_path_window_candidate(route,target_pair,crossings,config,rise,fall,
                                                      target_layer_id=target_layer_id)
            except ValueError as ex:
                stats['build_rejected']+=1
                stats['rejection_reasons'][str(ex)]=stats['rejection_reasons'].get(str(ex),0)+1
                continue
            if candidate.minimum_radius_mm<config.required_radius_mm:
                stats['curvature_rejected']+=1
                continue
            results.append(candidate)
        if len(results)>=cap:
            break
    pair_count=len(windows['rise'])*len(windows['fall'])
    stats['pair_count_before_rejection']=pair_count
    stats['cap_truncated']=max(0,pair_count-stats['curvature_rejected']-stats['build_rejected']
                               -len(results))
    stats['generated']=len(results)
    return results,stats


def candidate_path_offsets(model,candidate):
    """Canonical planar-offset key of a candidate's rise/fall windows, for BOTH
    the old line windows (primitive index + parameters) and the new path
    windows, so the two encodings can be deduplicated and compared."""
    rows=[]
    for window in (candidate.rise_window,candidate.fall_window):
        if not window:
            rows.append(None)
            continue
        if len(window)==4:
            i,u,j,v=window
            start=offset_of_primitive_parameter(model,i,u)
            end=offset_of_primitive_parameter(model,j,v)
        else:
            i,u,v=window
            start=offset_of_primitive_parameter(model,i,u)
            end=offset_of_primitive_parameter(model,i,v)
        rows.append((round(start,9),round(end,9)))
    return tuple(rows)


def candidate_window_kind(candidate):
    return getattr(candidate,'window_kind',WINDOW_KIND_LINE)
