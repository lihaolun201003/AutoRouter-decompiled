"""M1.6 sandbox only: no allocator, commit API, or baseline writes."""
from collections import Counter
from copy import deepcopy
from itertools import combinations
from src.models import ArcSegment2D
from src.router_2d import TrackAssignment, generate_assigned_routes_2d
from src.geometry import (smooth_orthogonal_route_2d, validate_smoothed_route_2d,
    arc_segment_radius, distance, smoothed_route_length)
from src.collision import find_smoothed_route_self_intersections_2d
from src.physical_intersections import find_physical_route_intersections_2d
from src.multi_crossing import classify_multi_crossing


def victim_scores(multis):
    return Counter(r for t in {tuple(sorted(t)) for t in multis} for r in t)


def victim_order(target, scores, special, alternate_counts):
    eligible = [r for r in target if r not in special]
    return sorted(eligible, key=lambda r: (scores[r], -alternate_counts[r], r))


def released_occupancy(occupancy, victim):
    if occupancy.count(victim) != 1:
        raise ValueError('Victim must own exactly one ordinary track')
    result = list(occupancy)
    result[result.index(victim)] = None
    return result


def candidate_geometry(waveguide, preparation, index, grid, special):
    if type(index) is not int or not 0 <= index < len(grid):
        raise ValueError('Track index outside grid')
    if waveguide.id in special:
        raise ValueError('Special victim excluded')
    w, p = deepcopy((waveguide, preparation))
    a = TrackAssignment(w.id, 'assigned', index, grid[index], None)
    skeleton = generate_assigned_routes_2d([w], [p], [a], top_y=150., bottom_y=0.)[0]
    curve = smooth_orthogonal_route_2d(skeleton, 5.)
    validate_smoothed_route_2d(curve)
    if not curve.segments or distance(curve.segments[0].start,w.start_port.position)>1e-9 or distance(curve.segments[-1].end,w.end_port.position)>1e-9:
        raise ValueError('Endpoint mismatch')
    if any(abs(arc_segment_radius(s)-5.)>1e-9 for s in curve.segments if isinstance(s,ArcSegment2D)):
        raise ValueError('Radius mismatch')
    if find_smoothed_route_self_intersections_2d(curve):
        raise ValueError('Self intersection')
    return curve


def local_pairs(candidate, routes):
    r = candidate.waveguide_id
    return {tuple(sorted((r,s))): find_physical_route_intersections_2d(candidate,routes[s])
            for s in sorted(routes) if s != r}


def local_multis(victim, delta, fixed_pairs):
    """Only single-CROSS triangles can be eligible; multiplicity is retained."""
    cross = {k:[e for e in v if e.kind=='cross'] for k,v in delta.items()}
    neighbors = sorted(next(x for x in k if x!=victim) for k,v in cross.items() if len(v)==1)
    result=set()
    for a,b in combinations(neighbors,2):
        ab = [e for e in fixed_pairs.get((a,b),()) if e.kind=='cross']
        if len(ab)!=1:
            continue
        ids=tuple(sorted((victim,a,b)))
        pairs={(a,b):ab,tuple(sorted((victim,a))):cross[tuple(sorted((victim,a)))],
               tuple(sorted((victim,b))):cross[tuple(sorted((victim,b)))]}
        if classify_multi_crossing(ids,pairs).classification=='multi_waveguide_crossing':
            result.add(ids)
    return result


def score_delta(target,victim,baseline_multis,after_local):
    old={t for t in baseline_multis if victim in t}
    removed=old-after_local
    added=after_local-old
    after=len(baseline_multis)-len(old)+len(after_local)
    return dict(target_multi_removed=tuple(sorted(target)) not in after_local,
        new_multi_created=len(added),old_multi_removed=len(removed),
        M_before=len(baseline_multis),M_after=after,
        removed=sorted(removed),added=sorted(added))


def acceptable(score, anomaly_free=True):
    return anomaly_free and score['target_multi_removed'] and score['M_after']<score['M_before']


def candidate_rank(score):
    return (score['M_after'],score['new_multi_created'],score['track_displacement'],score['track_index'])


def evaluate(target,victim,index,grid,occupancy,waveguides,preparations,routes,pairs,multis,special):
    """All writes target private objects. Exceptions discard them automatically."""
    temporary=released_occupancy(occupancy,victim)
    if type(index) is not int or not 0 <= index < len(grid) or len(grid)!=len(temporary):
        raise ValueError('Invalid track grid/index')
    if temporary[index] is not None:
        raise ValueError('Occupied track')
    curve=candidate_geometry(waveguides[victim],preparations[victim],index,grid,special)
    delta=local_pairs(curve,routes)
    after=local_multis(victim,delta,pairs)
    score=score_delta(target,victim,multis,after)
    # Saved baseline has zero inter-route TOUCH/OVERLAP; keep that existing state.
    anomalies=Counter(e.kind for v in delta.values() for e in v if e.kind!='cross')
    score.update(track_index=index,track_y=grid[index],track_displacement=abs(index-occupancy.index(victim)),
        length_delta_mm=smoothed_route_length(curve)-smoothed_route_length(routes[victim]),
        noncross_anomalies=dict(anomalies),physical_cross_count=sum(e.kind=='cross' for v in delta.values() for e in v),
        accepted=acceptable(score,not anomalies))
    return score,curve,delta
