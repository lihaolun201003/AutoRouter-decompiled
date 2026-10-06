"""Legacy three-cross-point criterion; not finite-width collision or clearance."""
from collections import Counter
from dataclasses import dataclass
from itertools import combinations
from math import isfinite
from typing import Iterable,Iterator
from .models import Point2D
from .geometry import distance
from .physical_intersections import PhysicalRouteIntersection


@dataclass
class MultiWaveguideCrossing:
    """One canonical graph triangle; outside-assumption cases have no selected points."""
    route_ids: tuple[int,int,int]
    point_ab: Point2D | None
    point_ac: Point2D | None
    point_bc: Point2D | None
    side_lengths_mm: tuple[float,float,float] | None
    short_side_count: int | None
    spacing_mm: float
    classification: str
    boundary_side_count: int = 0


def build_crossing_pair_map(
    events: Iterable[PhysicalRouteIntersection],
) -> dict[tuple[int,int],list[PhysicalRouteIntersection]]:
    """Keep all physical cross events, including pair multiplicity; ignore non-cross."""
    pairs={}
    for e in events:
        if e.kind!="cross":
            continue
        if e.route_a_id==e.route_b_id:
            raise ValueError("Cross must join distinct routes.")
        if not isinstance(e.point,Point2D) or not all(isfinite(v) for v in (e.point.x,e.point.y)):
            raise ValueError("Physical cross requires a finite Point2D.")
        key=tuple(sorted((e.route_a_id,e.route_b_id)))
        pairs.setdefault(key,[]).append(e)
    return dict(sorted(pairs.items()))


def audit_pair_multiplicity(pairs: dict) -> dict:
    """Counts and canonical top twenty pairs; no event is selected or removed."""
    counts=Counter(len(v) for v in pairs.values())
    if counts.get(0):
        raise ValueError("Crossing pair cannot have zero events.")
    return dict(cross_pairs_total=len(pairs),pairs_with_1_cross=counts[1],
        pairs_with_2_crosses=counts[2],pairs_with_3_or_more_crosses=sum(v for k,v in counts.items() if k>=3),
        pairs_with_multiple_crosses=sum(v for k,v in counts.items() if k>1),
        max_crosses_per_pair=max(counts,default=0),
        top20=[dict(route_ids=list(k),cross_count=len(v))
               for k,v in sorted(pairs.items(),key=lambda item:(-len(item[1]),item[0]))[:20]])


def build_crossing_graph(pairs: dict) -> dict[int,set[int]]:
    """Undirected adjacency sets; an edge represents at least one physical cross."""
    graph={}
    for (a,b),events in pairs.items():
        if a>=b or not events:
            raise ValueError("Expected canonical nonempty pair map.")
        graph.setdefault(a,set()).add(b)
        graph.setdefault(b,set()).add(a)
    return graph


def enumerate_crossing_triangles(graph: dict[int,set[int]]) -> Iterator[tuple[int,int,int]]:
    """Neighbor intersections enumerate each a<b<c exactly once."""
    for a in sorted(graph):
        for b in sorted(v for v in graph[a] if v>a):
            for c in sorted(v for v in graph[a].intersection(graph[b]) if v>b):
                yield a,b,c


def classify_multi_crossing(
    route_ids: tuple[int,int,int],pairs: dict,spacing_mm: float=0.125,tol: float=1e-9,
) -> MultiWaveguideCrossing:
    """Only lengths < spacing-tol count as short; equality is boundary.

    Two definite shorts prove multi even if the remaining side is boundary.
    Otherwise any boundary side gives boundary (not counted as multi), and
    other eligible triangles are not_multi_waveguide_crossing.
    """
    if not isfinite(spacing_mm) or spacing_mm<=0 or not isfinite(tol) or not 0<=tol<spacing_mm:
        raise ValueError("Require positive spacing and 0 <= tol < spacing.")
    ids=tuple(sorted(route_ids))
    if len(ids)!=3 or len(set(ids))!=3:
        raise ValueError("Expected three distinct route IDs.")
    edges=[pairs.get(key,[]) for key in combinations(ids,2)]
    if any(not edge for edge in edges):
        raise ValueError("Triplet is not a crossing graph triangle.")
    if any(len(edge)!=1 for edge in edges):
        return MultiWaveguideCrossing(ids,None,None,None,None,None,spacing_mm,
                                      "outside_legacy_single_cross_assumption")
    points=[Point2D(edge[0].point.x,edge[0].point.y) for edge in edges]
    lengths=tuple(distance(a,b) for a,b in combinations(points,2))
    if not all(isfinite(v) for v in lengths):
        raise ValueError("Nonfinite triangle side length.")
    short=sum(v<spacing_mm-tol for v in lengths)
    boundary=sum(abs(v-spacing_mm)<=tol for v in lengths)
    kind=("multi_waveguide_crossing" if short>=2 else
          "boundary" if boundary else "not_multi_waveguide_crossing")
    return MultiWaveguideCrossing(ids,*points,lengths,short,spacing_mm,kind,boundary)


def triplet_composition(route_ids: tuple[int,int,int],special_ids: set[int]) -> str:
    """Count independent special-Z membership without altering allocator status."""
    n=sum(i in special_ids for i in route_ids)
    return ("ordinary/ordinary/ordinary","ordinary/ordinary/special",
            "ordinary/special/special","special/special/special")[n]


def detect_multi_waveguide_crossings(
    events: Iterable[PhysicalRouteIntersection],spacing_mm: float=0.125,tol: float=1e-9,
) -> Iterator[MultiWaveguideCrossing]:
    """Yield every graph triangle, including boundary and outside-assumption records."""
    if not isfinite(spacing_mm) or spacing_mm<=0 or not isfinite(tol) or not 0<=tol<spacing_mm:
        raise ValueError("Invalid spacing or tolerance.")
    pairs=build_crossing_pair_map(events)
    for ids in enumerate_crossing_triangles(build_crossing_graph(pairs)):
        yield classify_multi_crossing(ids,pairs,spacing_mm,tol)
