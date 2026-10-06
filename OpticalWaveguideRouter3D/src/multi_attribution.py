"""Read-only post-hoc attribution of saved exact physical crossings.

No routing, intersection consolidation, or multi criterion is changed here.
Physical ownership is found by endpoint connectivity, never by arc index.
"""
from collections import defaultdict
from itertools import combinations
from math import atan2, cos, degrees, hypot, radians, sin

from .models import Point2D, LineSegment2D, ArcSegment2D, SmoothedRoute2D
from .collision import point_on_arc_2d
from .geometry import distance

TOL = 1e-9


def line_orientation(segment, tol=TOL):
    """Classify by displacement, retaining degenerate/nonaxis lines as OTHER."""
    dx, dy = segment.end.x-segment.start.x, segment.end.y-segment.start.y
    if abs(dy) <= tol and abs(dx) > tol:
        return "HORIZONTAL"
    if abs(dx) <= tol and abs(dy) > tol:
        return "VERTICAL"
    return "OTHER"


def physical_endpoints(waveguide, top_y=150., bottom_y=0., tol=TOL):
    """Copy real endpoint identities; physical labels do not use algorithmic order."""
    ports = (waveguide.start_port, waveguide.end_port)
    if not all(isinstance(p.position, Point2D) for p in ports):
        raise ValueError("Physical Point2D endpoints required.")
    result = []
    for i, p in enumerate(ports):
        other = ports[1-i]
        lr = ("SAME_X" if abs(p.position.x-other.position.x) <= tol else
              "LEFT" if p.position.x < other.position.x else "RIGHT")
        side = ("TOP" if abs(p.position.y-top_y) <= tol else
                "BOTTOM" if abs(p.position.y-bottom_y) <= tol else "AMBIGUOUS")
        result.append(dict(endpoint=f"endpoint_{i+1}", port_id=p.id, pmt_id=p.pmt_id,
                           x=p.position.x, y=p.position.y, physical_end=lr, side=side))
    return result


def geometric_pmt_order(waveguides, tol=TOL):
    """Reuse M1's same-side disjoint-x-range adjacency policy; no Dynamic-D call."""
    groups = defaultdict(list)
    for w in waveguides:
        for p in physical_endpoints(w, tol=tol):
            groups[p["pmt_id"]].append(p)
    orders = {}
    for side in ("TOP", "BOTTOM"):
        ranges = []
        for pid, ports in groups.items():
            sides = {p["side"] for p in ports}
            if len(sides) != 1 or "AMBIGUOUS" in sides:
                raise ValueError("Ambiguous PMT side.")
            if side in sides:
                ranges.append((min(p["x"] for p in ports), max(p["x"] for p in ports), pid))
        ranges.sort()
        if any(a[1] >= b[0] for a,b in zip(ranges, ranges[1:])):
            raise ValueError("Ambiguous geometric PMT ranges.")
        orders[side] = [r[2] for r in ranges]
    return orders


def neighbor_relation(owner_pmt, other_pmt, orders):
    """Relation of other PMT relative to an arc-owner PMT, by geometry only."""
    if owner_pmt is None or other_pmt is None:
        return "AMBIGUOUS"
    if owner_pmt == other_pmt:
        return "SAME_PMT"
    for ids in orders.values():
        if owner_pmt in ids:
            if other_pmt not in ids:
                return "NON_ADJACENT"
            delta = ids.index(other_pmt)-ids.index(owner_pmt)
            return "LEFT_GEOMETRIC_NEIGHBOR" if delta == -1 else (
                "RIGHT_GEOMETRIC_NEIGHBOR" if delta == 1 else "NON_ADJACENT")
    return "AMBIGUOUS"


def deserialize_plot(record):
    """Decode the saved analytic circle representation; do not generate a route."""
    segments = []
    for s in record["segments"]:
        if s["kind"] == "line":
            segments.append(LineSegment2D(Point2D(s["x1"],s["y1"]),Point2D(s["x2"],s["y2"])))
        elif s["kind"] == "arc":
            a,b = radians(s["start_deg"]),radians(s["start_deg"]+s["sweep_deg"])
            segments.append(ArcSegment2D(
                Point2D(s["cx"]+s["r"]*cos(a),s["cy"]+s["r"]*sin(a)),
                Point2D(s["cx"]+s["r"]*cos(b),s["cy"]+s["r"]*sin(b)),
                Point2D(s["cx"],s["cy"]),radians(s["sweep_deg"])))
        else:
            raise ValueError("Unknown primitive kind.")
    return SmoothedRoute2D(record["id"], segments)


def chain_ownership(route, endpoints, tol=TOL):
    """Follow unique geometric connectivity; preserve storage indices in output.

    First arc reached from each physical endpoint through only connected lines
    is its bend. Interior arcs are not assigned by distance. Multiple reachable
    owners remain ambiguous. Permuting storage order is supported if connectivity
    still forms one unique open chain.
    """
    point = Point2D(endpoints[0]["x"],endpoints[0]["y"])
    remaining = set(range(len(route.segments)))
    chain = []
    while remaining:
        options = []
        for i in remaining:
            s = route.segments[i]
            if distance(point,s.start) <= tol:
                options.append((i,s.end))
            if distance(point,s.end) <= tol:
                options.append((i,s.start))
        if len(options) != 1:
            raise ValueError("Primitive chain is disconnected, branched or degenerate.")
        i,point = options[0]
        chain.append(i)
        remaining.remove(i)
    if distance(point,Point2D(endpoints[1]["x"],endpoints[1]["y"])) > tol:
        raise ValueError("Primitive chain does not terminate at the other physical endpoint.")
    owners = defaultdict(list)
    for order, endpoint in ((chain,endpoints[0]),(list(reversed(chain)),endpoints[1])):
        for i in order:
            owners[i].append(endpoint.copy())
            if isinstance(route.segments[i],ArcSegment2D):
                break
    return dict(owners)


def primitive_description(route, index, owners):
    """Describe geometry plus unambiguous endpoint ownership, if available."""
    s = route.segments[index]
    candidates = owners.get(index,[])
    owner = candidates[0].copy() if len(candidates) == 1 else None
    result = dict(segment_index=index, type="ARC" if isinstance(s,ArcSegment2D) else "LINE",
                  orientation=None if isinstance(s,ArcSegment2D) else line_orientation(s),
                  endpoint_owner=owner,
                  ownership_status="ENDPOINT_CONNECTED" if owner else (
                      "AMBIGUOUS" if candidates else "INTERIOR"),
                  owner_candidates=[p.copy() for p in candidates])
    if isinstance(s,ArcSegment2D):
        result.update(center=dict(x=s.center.x,y=s.center.y),
                      radius=hypot(s.start.x-s.center.x,s.start.y-s.center.y),
                      start_angle_rad=atan2(s.start.y-s.center.y,s.start.x-s.center.x),
                      end_angle_rad=atan2(s.end.y-s.center.y,s.end.x-s.center.x),
                      sweep_rad=s.sweep_rad)
    return result


def point_on_primitive(point, segment, tol=TOL):
    """Validate attribution against analytic geometry, including nonaxis lines."""
    if isinstance(segment,ArcSegment2D):
        return point_on_arc_2d(point,segment,tol)
    dx,dy=segment.end.x-segment.start.x,segment.end.y-segment.start.y
    length=hypot(dx,dy)
    if length <= tol:
        return distance(point,segment.start) <= tol
    px,py=point.x-segment.start.x,point.y-segment.start.y
    projection=(px*dx+py*dy)/length
    return abs(px*dy-py*dx)/length <= tol and -tol <= projection <= length+tol


def primitive_attribution(route, point, raw_indices, owners, tol=TOL):
    """Keep all join memberships rather than arbitrarily choosing Line vs Arc."""
    members = [i for i,s in enumerate(route.segments) if point_on_primitive(point,s,tol)]
    if not members or not set(raw_indices) <= set(members):
        raise ValueError("Saved physical/raw point disagrees with saved geometry.")
    return [primitive_description(route,i,owners) for i in members]


def primitive_token(p, detailed=False):
    token = "ARC" if p["type"] == "ARC" else p["orientation"]
    if detailed and p["type"] == "ARC":
        o=p["endpoint_owner"]
        token += "("+(o["physical_end"]+":"+o["side"] if o else p["ownership_status"])+")"
    return token


def pair_token(cross, detailed=False):
    def token(items):
        return "+".join(sorted({primitive_token(p,detailed) for p in items}))
    return " x ".join(sorted((token(cross["primitive_a"]),token(cross["primitive_b"]))))


def topology_signature(crosses, detailed=True):
    """Canonical unordered multiset; independent of route/pair traversal order."""
    return " | ".join(sorted(pair_token(c,detailed) for c in crosses))


def arc_vertical_relations(cross, orders):
    """Emit one relation per unambiguous endpoint Arc/vertical counterpart."""
    results=[]
    for arc_key,line_key,arc_route,line_route in (
        ("primitive_a","primitive_b",cross["route_a"],cross["route_b"]),
        ("primitive_b","primitive_a",cross["route_b"],cross["route_a"])):
        for a in cross[arc_key]:
            if a["type"] != "ARC" or not a["endpoint_owner"]:
                continue
            for v in cross[line_key]:
                if v["type"] != "LINE" or v["orientation"] != "VERTICAL":
                    continue
                vo=v["endpoint_owner"]
                results.append(dict(arc_route=arc_route,arc_segment=a["segment_index"],
                    arc_owner=a["endpoint_owner"].copy(),vertical_route=line_route,
                    vertical_owner=vo.copy() if vo else None,
                    neighbor_relation=neighbor_relation(a["endpoint_owner"]["pmt_id"],
                        vo["pmt_id"] if vo else None,orders)))
    return results


def classify_paper_like(crosses, legacy_eligible=True):
    """Conservative post-hoc label, not a routing rule or a new multi criterion.

    A-E are required. A strict H/V + Arc/V + Arc/H motif with one repeated bend
    supports the paper illustration. A-E-compatible other motifs stay ambiguous.
    """
    if not legacy_eligible:
        return dict(label="NON_PAPER_LIKE",reason="NOT_LEGACY_ELIGIBLE",witnesses=[])
    if any(len(c[k]) != 1 for c in crosses for k in ("primitive_a","primitive_b")):
        return dict(label="PAPER_LIKE_AMBIGUOUS",reason="PRIMITIVE_JOIN_MEMBERSHIP",witnesses=[])
    ids=sorted({c[k] for c in crosses for k in ("route_a","route_b")})
    carriers=[]
    for rid in ids:
        uses=[(c,c["primitive_a"][0] if c["route_a"]==rid else c["primitive_b"][0])
              for c in crosses if rid in (c["route_a"],c["route_b"])]
        if len(uses)==2 and all(p["type"]=="LINE" and p["orientation"]=="VERTICAL" for _,p in uses):
            carriers.append(rid)
    if not carriers:
        return dict(label="NON_PAPER_LIKE",reason="NO_TWO_CROSS_VERTICAL_CARRIER",witnesses=[])
    relations=[r for c in crosses for r in c["neighbor_relations"] if r["vertical_route"] in carriers]
    witnesses=[r for r in relations if r["neighbor_relation"] in (
        "LEFT_GEOMETRIC_NEIGHBOR","RIGHT_GEOMETRIC_NEIGHBOR")]
    if not witnesses:
        ambiguous=any(r["neighbor_relation"]=="AMBIGUOUS" for r in relations)
        return dict(label="PAPER_LIKE_AMBIGUOUS" if ambiguous else "NON_PAPER_LIKE",
                    reason="AMBIGUOUS_ADJACENCY" if ambiguous else "NO_ADJACENT_ENDPOINT_BEND",
                    witnesses=[])
    expected=sorted(("ARC x HORIZONTAL","ARC x VERTICAL","HORIZONTAL x VERTICAL"))
    arc_uses=[(c[k],p["segment_index"]) for c in crosses
              for k,pk in (("route_a","primitive_a"),("route_b","primitive_b"))
              for p in c[pk] if p["type"]=="ARC"]
    if sorted(pair_token(c) for c in crosses)==expected and len(set(arc_uses))==1 and len(witnesses)==1:
        return dict(label="PAPER_LIKE_LOCAL_MULTI",reason="UNIQUE_ADJACENT_HV_AV_AH_MOTIF",witnesses=witnesses)
    return dict(label="PAPER_LIKE_AMBIGUOUS",reason="AE_COMPATIBLE_BUT_NOT_UNIQUE_PAPER_MOTIF",witnesses=witnesses)
