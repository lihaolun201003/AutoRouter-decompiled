"""Deterministic Step 8.5-E integration audit; no routing changes or source writes."""
import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
from itertools import combinations
import json
from math import hypot, isfinite
from pathlib import Path
from time import perf_counter
from src.io import load_legacy_512_snapshot
from src.models import LineSegment2D, ArcSegment2D
from src.router_2d import (
    prepare_waveguides_2d, assign_tracks_2d, TrackPolicyConfig,
    generate_assigned_routes_2d,
)
from src.geometry import (
    smooth_orthogonal_route_2d, build_special_z_smoothed_route_2d,
    validate_smoothed_route_2d, arc_segment_radius, smoothed_route_length,
)
from src.collision import (
    find_smoothed_route_intersections_2d, find_smoothed_route_self_intersections_2d,
)

KINDS = ("cross", "touch", "overlap")


def tangent(segment, end=False):
    """Unit travel tangent at the requested endpoint."""
    p = segment.end if end else segment.start
    if isinstance(segment, LineSegment2D):
        x,y = segment.end.x-segment.start.x,segment.end.y-segment.start.y
    else:
        sign = 1 if segment.sweep_rad > 0 else -1
        x,y = -sign*(p.y-segment.center.y),sign*(p.x-segment.center.x)
    length=hypot(x,y)
    return x/length,y/length


def check_route(route, waveguide, radius=5.0, tol=1e-9):
    """Collect per-route reasons without repairing geometry."""
    errors=[]
    try:
        validate_smoothed_route_2d(route,tol)
        assert route.segments, "empty geometry"
        assert route.segments[0].start == waveguide.start_port.position, "start changed"
        assert route.segments[-1].end == waveguide.end_port.position, "end changed"
        for s in route.segments:
            if isinstance(s,ArcSegment2D):
                assert abs(arc_segment_radius(s)-radius)<=tol, "radius mismatch"
        for a,b in zip(route.segments,route.segments[1:]):
            ta,tb=tangent(a,True),tangent(b)
            assert hypot(ta[0]-tb[0],ta[1]-tb[1])<=tol, "tangent discontinuity"
        length=smoothed_route_length(route)
        assert isfinite(length) and length>0, "invalid total length"
    except (ValueError,TypeError,AssertionError,ArithmeticError) as exc:
        errors.append(type(exc).__name__+": "+str(exc))
    return errors


def empty_stats():
    return dict(pair_count=0, cross_events=0,touch_events=0,overlap_events=0,
                cross_pairs=0,touch_pairs=0,overlap_pairs=0,any_pairs=0)


def add_stats(stats,events):
    stats["pair_count"]+=1
    counts=Counter(e.kind for e in events)
    for kind in KINDS:
        stats[kind+"_events"]+=counts[kind]
        stats[kind+"_pairs"]+=int(counts[kind]>0)
    stats["any_pairs"]+=bool(events)


def validate(fiberboard, snapshot, output):
    """Run all pairs, retain errors/events, and assert integration invariants."""
    started=perf_counter()
    paths=[fiberboard,snapshot]
    hashes=[sha256(p.read_bytes()).hexdigest() for p in paths]
    ws=load_legacy_512_snapshot(fiberboard,snapshot)
    original_ws=deepcopy(ws)
    config=TrackPolicyConfig(150.0,0.05,0.125,5.0)
    preps=prepare_waveguides_2d(ws,150.0,0.0)
    assignments=assign_tracks_2d(ws,preps,config)
    originals=deepcopy((preps,assignments))
    statuses=Counter(a.status for a in assignments)
    assert statuses=={"assigned":454,"unsupported_geometry":58}, statuses
    skeletons=generate_assigned_routes_2d(ws,preps,assignments,top_y=150.0,bottom_y=0.0)
    by_id={w.id:w for w in ws}
    special_ids={a.waveguide_id for a in assignments if a.status=="unsupported_geometry"}
    routes=[]
    failures=[]
    for skeleton in skeletons:
        try:
            routes.append(smooth_orthogonal_route_2d(skeleton,5.0))
        except Exception as exc:
            failures.append(dict(id=skeleton.waveguide_id,stage="construction",reason=repr(exc)))
    ordinary=list(routes)
    for identifier in sorted(special_ids):
        w=by_id[identifier]
        try:
            routes.append(build_special_z_smoothed_route_2d(identifier,w.start_port.position,w.end_port.position,5.0))
        except Exception as exc:
            failures.append(dict(id=identifier,stage="construction",reason=repr(exc)))
    ids=[r.waveguide_id for r in routes]
    assert len(ids)==len(set(ids)), "duplicate geometry IDs"
    saved_routes=deepcopy(routes)
    saved_skeletons=deepcopy(skeletons)
    self_events=[]
    valid=0
    for r in routes:
        reasons=check_route(r,by_id[r.waveguide_id])
        if reasons:
            failures.append(dict(id=r.waveguide_id,stage="geometry",reason=reasons))
        else:
            valid+=1
        try:
            self_events.extend(asdict(e) for e in find_smoothed_route_self_intersections_2d(r))
        except Exception as exc:
            failures.append(dict(id=r.waveguide_id,stage="self",reason=repr(exc)))
    print("geometry",len(routes),"valid",valid,"errors",len(failures),flush=True)
    groups={name:empty_stats() for name in ("ordinary-ordinary","ordinary-special","special-special")}
    global_stats=empty_stats()
    burden={identifier:dict(waveguide_id=identifier,special=identifier in special_ids,
                           cross_events=0,cross_pairs=0,touch_events=0,overlap_events=0)
            for identifier in ids}
    output.mkdir(parents=True,exist_ok=True)
    event_path=output/"step_8_5_legacy_512_exact_events.jsonl"
    pair_errors=[]
    collision_start=perf_counter()
    with event_path.open("w",encoding="utf-8") as event_file:
        for a,b in combinations(routes,2):
            n=int(a.waveguide_id in special_ids)+int(b.waveguide_id in special_ids)
            group=("ordinary-ordinary","ordinary-special","special-special")[n]
            try:
                events=find_smoothed_route_intersections_2d(a,b)
            except Exception as exc:
                pair_errors.append(dict(a=a.waveguide_id,b=b.waveguide_id,reason=repr(exc)))
                # Failed calls are counted separately, never treated as disjoint.
                continue
            add_stats(global_stats,events)
            add_stats(groups[group],events)
            counts=Counter(e.kind for e in events)
            for identifier in (a.waveguide_id,b.waveguide_id):
                for kind in KINDS:
                    burden[identifier][kind+"_events"]+=counts[kind]
                burden[identifier]["cross_pairs"]+=bool(counts["cross"])
            for e in events:
                event_file.write(json.dumps(asdict(e),sort_keys=True)+"\n")
            if global_stats["pair_count"]%20000==0:
                print("pairs",global_stats["pair_count"],"seconds",round(perf_counter()-collision_start,2),flush=True)
    seconds=perf_counter()-collision_start
    # Independent ordinary-only invocation, not merely copying the group counters.
    t=perf_counter()
    ordinary_stats=empty_stats()
    for a,b in combinations(ordinary,2):
        add_stats(ordinary_stats,find_smoothed_route_intersections_2d(a,b))
    ordinary_seconds=perf_counter()-t
    assert ordinary_stats==groups["ordinary-ordinary"]
    unchanged=(ws==original_ws and (preps,assignments)==originals
               and routes==saved_routes and skeletons==saved_skeletons
               and hashes==[sha256(p.read_bytes()).hexdigest() for p in paths])
    checks=dict(ordinary_454=len(ordinary)==454,special_58=len(routes)-len(ordinary)==58,
                total_512=len(routes)==512,unique_ids=len(set(ids))==512,
                id_coverage=set(ids)==set(by_id),geometry_all_valid=valid==512,
                full_pairs=global_stats["pair_count"]==130816,
                collision_completed=not pair_errors,inputs_unchanged=unchanged,
                allocator_unchanged=assignments==originals[1] and
                Counter(a.status for a in assignments)==statuses)
    result=dict(
        sources=[dict(path=str(p),sha256=h) for p,h in zip(paths,hashes)],
        config=asdict(config),allocator_assigned=statuses["assigned"],
        allocator_unsupported_special_z=statuses["unsupported_geometry"],
        analytic_geometry_available=len(routes),valid_geometry=valid,
        invalid_geometry=len(routes)-valid,failures=failures,
        self_events=self_events,self_counts={k:sum(e["kind"]==k for e in self_events) for k in KINDS},
        global_stats=global_stats,groups=groups,ordinary_separate=ordinary_stats,
        pair_errors=pair_errors,per_waveguide=[burden[k] for k in sorted(burden)],
        top10=sorted(burden.values(),key=lambda v:(-v["cross_events"],v["waveguide_id"]))[:10],
        special_with_cross=sum(burden[k]["cross_events"]>0 for k in special_ids if k in burden),
        collision_seconds=seconds,ordinary_separate_seconds=ordinary_seconds,
        total_seconds=perf_counter()-started,checks=checks,
        raw_events_path=str(event_path),
    )
    (output/"step_8_5_legacy_512_exact_summary.json").write_text(
        json.dumps(result,indent=2,ensure_ascii=True),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in
        ("per_waveguide","self_events","sources")},indent=2),flush=True)
    assert all(checks.values()) and not failures, "Integration checks failed; see saved diagnostics"
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fiberboard",type=Path)
    parser.add_argument("snapshot",type=Path)
    args=parser.parse_args()
    validate(args.fiberboard,args.snapshot,Path(__file__).resolve().parents[1]/"outputs")


if __name__=="__main__":
    main()
