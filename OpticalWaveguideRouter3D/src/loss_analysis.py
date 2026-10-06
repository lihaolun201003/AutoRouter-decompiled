"""Known non-crossing losses for explicitly millimetre-valued analytic geometry."""
from math import degrees,fsum,isfinite,pi
from statistics import mean,median
from . import loss
from .models import SmoothedRoute2D,ArcSegment2D,LineSegment2D
from .geometry import validate_smoothed_route_2d,line_segment_length,arc_segment_length,arc_segment_radius


def analyze_route_loss_mm(route: SmoothedRoute2D, radius_mm: float=5.0, tol: float=1e-9) -> dict:
    """Validate measured arc radii against the supplied table radius; never interpolate."""
    validate_smoothed_route_2d(route,tol)
    lines=[s for s in route.segments if isinstance(s,LineSegment2D)]
    arcs=[s for s in route.segments if isinstance(s,ArcSegment2D)]
    for arc in arcs:
        if abs(arc_segment_radius(arc)-radius_mm)>tol:
            raise ValueError("Arc radius differs from configured table radius.")
    # Radius is configured, not rounded to the nearest table entry. This handles
    # floating-point construction residuals while retaining the strict loss API.
    bends=[(radius_mm,degrees(abs(s.sweep_rad))) for s in arcs]
    line_mm=fsum(line_segment_length(s) for s in lines)
    arc_mm=fsum(arc_segment_length(s) for s in arcs)
    total=fsum((line_mm,arc_mm))
    if not isfinite(total) or total<=0:
        raise ValueError("Expected positive finite route length.")
    propagation=loss.propagation_loss(total/10.0)
    bend=loss.total_bend_loss(bends)
    return dict(waveguide_id=route.waveguide_id,line_length_mm=line_mm,arc_length_mm=arc_mm,
                total_length_mm=total,propagation_loss_db=propagation,arc_count=len(arcs),
                total_bend_angle_rad=fsum(abs(s.sweep_rad) for s in arcs),bend_loss_db=bend,
                known_non_crossing_loss_db=propagation+bend)


def statistics(values: list[float]) -> dict:
    """Empty samples have null statistics, never an invented zero angle."""
    if not values:
        return dict(count=0,min=None,max=None,mean=None,median=None,sum=0)
    return dict(count=len(values),min=min(values),max=max(values),mean=mean(values),
                median=median(values),sum=fsum(values))


def crossing_angle_statistics(events: list[dict], route_ids: list[int]) -> dict:
    """Consume physical JSON-compatible events; no crossing loss calculation."""
    if len(route_ids)!=len(set(route_ids)):
        raise ValueError("Duplicate route IDs.")
    per={i:[] for i in route_ids}
    angles=[]
    for e in events:
        if e["kind"]!="cross":
            continue
        angle=e["crossing_angle_rad"]
        if angle is None or not isfinite(angle) or not 0<=angle<=pi/2:
            raise ValueError("Invalid physical crossing angle.")
        a,b=e["route_a_id"],e["route_b_id"]
        if a==b or a not in per or b not in per:
            raise ValueError("Invalid physical pair IDs.")
        value=degrees(angle)
        angles.append(value)
        per[a].append(value);per[b].append(value)
    hist=[0]*9
    for value in angles:
        hist[min(int(value/10),8)]+=1
    return dict(degrees=statistics(angles),
                histogram=[dict(lower_deg=i*10,upper_deg=(i+1)*10,count=n)
                           for i,n in enumerate(hist)],
                histogram_rule="[lower, upper), except final [80,90]",
                coarse=dict(below_30=sum(a<30 for a in angles),
                            from_30_through_60=sum(30<=a<=60 for a in angles),
                            above_60=sum(a>60 for a in angles)),
                per_waveguide={i:dict(physical_cross_count=len(v),
                    crossing_angle_min_deg=min(v) if v else None,
                    crossing_angle_max_deg=max(v) if v else None,
                    crossing_angle_mean_deg=mean(v) if v else None) for i,v in per.items()})
