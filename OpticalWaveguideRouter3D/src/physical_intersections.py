"""Route-pair discrete intersection consolidation above analytic segment events."""
from dataclasses import dataclass
from math import atan2, hypot, isfinite
from .models import Point2D, LineSegment2D, ArcSegment2D, SmoothedRoute2D
from .geometry import distance, validate_smoothed_route_2d, arc_segment_radius
from .collision import CurveRouteIntersection, find_smoothed_route_intersections_2d


@dataclass
class PhysicalRouteIntersection:
    """Pair-local point, travel tangents and unsigned acute angle; overlap has no point."""
    route_a_id: int
    route_b_id: int
    point: Point2D | None
    kind: str
    tangent_a: tuple[float,float] | None = None
    tangent_b: tuple[float,float] | None = None
    crossing_angle_rad: float | None = None
    raw_event_count: int = 1


def _unit_tangent(segment: LineSegment2D | ArcSegment2D, point: Point2D) -> tuple[float,float]:
    if isinstance(segment,LineSegment2D):
        x,y=segment.end.x-segment.start.x,segment.end.y-segment.start.y
    else:
        sign=1 if segment.sweep_rad>0 else -1
        x,y=-sign*(point.y-segment.center.y),sign*(point.x-segment.center.x)
    length=hypot(x,y)
    if not isfinite(length) or length==0:
        raise ValueError("Undefined travel tangent.")
    return x/length,y/length


def _local_tangent(
    route: SmoothedRoute2D, point: Point2D, indices: list[int],
    tol: float, angular_tol: float,
) -> tuple[float,float]:
    # Raw indices identify the occurrence; include adjacent pieces even if a
    # numerical candidate was emitted for only one side of the join.
    indices=set(indices)
    for i in list(indices):
        segment=route.segments[i]
        if i>0 and distance(point,segment.start)<=tol:
            indices.add(i-1)
        if i+1<len(route.segments) and distance(point,segment.end)<=tol:
            indices.add(i+1)
    ordered=sorted(indices)
    if any(b!=a+1 for a,b in zip(ordered,ordered[1:])):
        raise ValueError("Multiple nonadjacent route occurrences at one point.")
    vectors=[]
    allowances=[]
    for i in ordered:
        segment=route.segments[i]
        p=point
        # Evaluate exact join tangent when the representative is within tol.
        if distance(point,segment.start)<=tol:
            p=segment.start
        elif distance(point,segment.end)<=tol:
            p=segment.end
        vectors.append(_unit_tangent(segment,p))
        allowances.append(tol/arc_segment_radius(segment) if isinstance(segment,ArcSegment2D) else 0.0)
    first=vectors[0]
    for vector,allowance in zip(vectors[1:],allowances[1:]):
        if hypot(vector[0]-first[0],vector[1]-first[1])>angular_tol+allowance+allowances[0]:
            raise ValueError("Route does not have a unique smooth travel tangent at intersection.")
    return first


def consolidate_route_intersections_2d(
    a: SmoothedRoute2D,b: SmoothedRoute2D,events: list[CurveRouteIntersection],
    tol: float=1e-9,angular_tol: float=1e-9,
) -> list[PhysicalRouteIntersection]:
    """Consolidate events for ONE unordered pair without changing raw events.

    Coordinate clusters are deterministic complete-link clusters: every point
    must be within tol of every existing member (no transitive tolerance chain).
    Route endpoints remain touch. Interior points cross iff unit tangents are
    nonparallel; parallel/antiparallel isolated contacts are touch.
    Overlap records are preserved individually; no interval union is attempted.
    Nonsmooth joins and multiple route occurrences raise ValueError.
    """
    if any(not isfinite(v) or v<0 for v in (tol,angular_tol)):
        raise ValueError("Tolerances must be finite and nonnegative.")
    validate_smoothed_route_2d(a,tol)
    validate_smoothed_route_2d(b,tol)
    if a.waveguide_id==b.waveguide_id:
        raise ValueError("Distinct route IDs required.")
    # Canonical pair orientation makes swapping arguments deterministic.
    if a.waveguide_id>b.waveguide_id:
        a,b=b,a
    normalized=[]
    for event in events:
        if (event.route_id_a,event.route_id_b)==(a.waveguide_id,b.waveguide_id):
            i,j=event.segment_index_a,event.segment_index_b
        elif (event.route_id_b,event.route_id_a)==(a.waveguide_id,b.waveguide_id):
            i,j=event.segment_index_b,event.segment_index_a
        else:
            raise ValueError("Event belongs to a different route pair.")
        if not 0<=i<len(a.segments) or not 0<=j<len(b.segments):
            raise ValueError("Invalid segment index.")
        if event.kind not in ("cross","touch","overlap"):
            raise ValueError("Unexpected raw event kind.")
        if (event.kind=="overlap") != (event.point is None):
            raise ValueError("Raw event point/kind mismatch.")
        normalized.append((event,i,j))
    result=[PhysicalRouteIntersection(a.waveguide_id,b.waveguide_id,None,"overlap")
            for e,i,j in normalized if e.kind=="overlap"]
    discrete=sorted((item for item in normalized if item[0].point is not None),
                    key=lambda item:(item[0].point.x,item[0].point.y,item[1],item[2]))
    clusters=[]
    for item in discrete:
        for cluster in clusters:
            if all(distance(item[0].point,old[0].point)<=tol for old in cluster):
                cluster.append(item)
                break
        else:
            clusters.append([item])
    for cluster in clusters:
        source=cluster[0][0].point
        point=Point2D(source.x,source.y)
        ta=_local_tangent(a,point,[i for e,i,j in cluster],tol,angular_tol)
        tb=_local_tangent(b,point,[j for e,i,j in cluster],tol,angular_tol)
        cross=abs(ta[0]*tb[1]-ta[1]*tb[0])
        dot=abs(ta[0]*tb[0]+ta[1]*tb[1])
        angle=atan2(cross,dot)
        endpoint=any(distance(point,p)<=tol for r in (a,b)
                     for p in (r.segments[0].start,r.segments[-1].end))
        kind="touch" if endpoint or cross<=angular_tol else "cross"
        result.append(PhysicalRouteIntersection(a.waveguide_id,b.waveguide_id,
                       point,kind,ta,tb,angle,len(cluster)))
    return result


def find_physical_route_intersections_2d(
    a: SmoothedRoute2D,b: SmoothedRoute2D,tol: float=1e-9,angular_tol: float=1e-9,
) -> list[PhysicalRouteIntersection]:
    """Obtain raw analytic events then consolidate within this route pair only."""
    return consolidate_route_intersections_2d(
        a,b,find_smoothed_route_intersections_2d(a,b,tol),tol,angular_tol)
