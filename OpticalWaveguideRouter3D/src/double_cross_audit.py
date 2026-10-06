"""Diagnostic helpers for exactly-two physical crossings; no routing mutation."""
from math import atan2,tau,isfinite
from .geometry import distance,line_segment_length,arc_segment_length,smoothed_route_length
from .models import LineSegment2D,SmoothedRoute2D,Point2D


def split_cross_pairs(events: list[dict]) -> dict:
    pairs={}
    for e in events:
        if e["kind"]=="cross":
            key=tuple(sorted((e["route_a_id"],e["route_b_id"])))
            pairs.setdefault(key,[]).append(e)
    return {name:{k:v for k,v in sorted(pairs.items()) if condition(len(v))}
            for name,condition in (("single",lambda n:n==1),("double",lambda n:n==2),("higher",lambda n:n>2))}


def route_pair_type(a: str,b: str) -> str:
    values=sorted("U" if x in ("topU","bottomU") else "Z" for x in (a,b))
    return "-".join(values)


def geometry_composition(a_special: bool,b_special: bool) -> str:
    return ("ordinary-ordinary","ordinary-special","special-special")[a_special+b_special]


def segment_topology(types_a: set[str],types_b: set[str]) -> str:
    """Retain join ambiguity instead of pretending a join is only Line or Arc."""
    def label(values):
        return "/".join(sorted(t.replace("Segment2D","") for t in values))
    return "-".join(sorted((label(types_a),label(types_b))))


def normalized_progress(route: SmoothedRoute2D,point: Point2D,index: int,tol: float=1e-9) -> float:
    """Analytic travel arclength for a point on the indicated segment."""
    lengths=[line_segment_length(s) if isinstance(s,LineSegment2D) else arc_segment_length(s)
             for s in route.segments]
    s=route.segments[index]
    if distance(point,s.start)<=tol:
        local=0.0
    elif distance(point,s.end)<=tol:
        local=lengths[index]
    elif isinstance(s,LineSegment2D):
        ux=(s.end.x-s.start.x)/lengths[index];uy=(s.end.y-s.start.y)/lengths[index]
        local=(point.x-s.start.x)*ux+(point.y-s.start.y)*uy
        if abs((point.x-s.start.x)*uy-(point.y-s.start.y)*ux)>tol:
            raise ValueError("Point is off line.")
    else:
        start=atan2(s.start.y-s.center.y,s.start.x-s.center.x)
        angle=atan2(point.y-s.center.y,point.x-s.center.x)
        delta=((angle-start) if s.sweep_rad>0 else (start-angle))%tau
        radius=distance(s.start,s.center)
        if abs(distance(point,s.center)-radius)>tol:
            raise ValueError("Point is off circle.")
        local=radius*delta
    if not -tol<=local<=lengths[index]+tol:
        raise ValueError("Point lies outside segment.")
    return (sum(lengths[:index])+min(max(local,0),lengths[index]))/sum(lengths)


def skeleton_comparison(cross_count: int,touch_count: int=0,overlap_count: int=0) -> str:
    if touch_count or overlap_count or cross_count not in (0,1,2):
        return "other"
    return f"skeleton_{cross_count}_to_smooth_2"


def track_difference(a: int,b: int) -> int:
    if a==b:raise ValueError("Distinct assigned routes share a track.")
    return abs(a-b)


def category_range_overlap(ranges: dict) -> dict:
    """Closed index hull overlap, not a claim about full routed geometry overlap."""
    return {a:{b:not (ra["max_index"]<rb["min_index"] or rb["max_index"]<ra["min_index"])
               for b,rb in ranges.items()} for a,ra in ranges.items()}
