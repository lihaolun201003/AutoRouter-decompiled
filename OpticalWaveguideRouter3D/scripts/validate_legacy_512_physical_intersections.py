"""Step 8.5-E.1 deterministic route-level physical intersection audit."""
import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
from time import perf_counter
from src.io import load_legacy_512_snapshot
from src.router_2d import prepare_waveguides_2d,assign_tracks_2d,TrackPolicyConfig,generate_assigned_routes_2d
from src.geometry import smooth_orthogonal_route_2d,build_special_z_smoothed_route_2d
from src.collision import find_smoothed_route_intersections_2d
from src.physical_intersections import consolidate_route_intersections_2d
from scripts.validate_legacy_512_exact import check_route,empty_stats,add_stats


def validate(fiberboard: Path,snapshot: Path,output: Path) -> dict:
    started=perf_counter()
    hashes=[sha256(p.read_bytes()).hexdigest() for p in (fiberboard,snapshot)]
    ws=load_legacy_512_snapshot(fiberboard,snapshot)
    saved_ws=deepcopy(ws)
    preps=prepare_waveguides_2d(ws,150.0,0.0)
    assignments=assign_tracks_2d(ws,preps,TrackPolicyConfig(150,0.05,0.125,5))
    saved_allocation=deepcopy((preps,assignments))
    assert Counter(a.status for a in assignments)=={"assigned":454,"unsupported_geometry":58}
    special={a.waveguide_id for a in assignments if a.status=="unsupported_geometry"}
    skeletons=generate_assigned_routes_2d(ws,preps,assignments,top_y=150,bottom_y=0)
    routes=[smooth_orthogonal_route_2d(r,5) for r in skeletons]
    by_id={w.id:w for w in ws}
    routes += [build_special_z_smoothed_route_2d(i,by_id[i].start_port.position,by_id[i].end_port.position,5)
               for i in sorted(special)]
    assert len(routes)==len({r.waveguide_id for r in routes})==512
    for r in routes:
        assert not check_route(r,by_id[r.waveguide_id]), r.waveguide_id
    saved_routes=deepcopy(routes)
    raw_stats=empty_stats()
    physical_stats=empty_stats()
    names=("ordinary-ordinary","ordinary-special","special-special")
    groups={name:{"raw":empty_stats(),"physical":empty_stats()} for name in names}
    targets={(20,257),(22,259),(224,466)}
    midpoint=[]
    duplicate_cross_removed=0
    raw_cross_clusters=0
    raw_touch_to_cross=0
    errors=[]
    output.mkdir(parents=True,exist_ok=True)
    events_path=output/"step_8_5_legacy_512_physical_events.jsonl"
    loop=perf_counter()
    with events_path.open("w",encoding="utf-8") as sink:
        for a,b in combinations(routes,2):
            pair=tuple(sorted((a.waveguide_id,b.waveguide_id)))
            group=names[int(a.waveguide_id in special)+int(b.waveguide_id in special)]
            raw=find_smoothed_route_intersections_2d(a,b)
            before=deepcopy(raw)
            add_stats(raw_stats,raw)
            add_stats(groups[group]["raw"],raw)
            try:
                physical=consolidate_route_intersections_2d(a,b,raw)
                # Reuse the same deterministic grouping rule for cross-only
                # diagnostics; adjacent membership still comes from the route.
                cross_only=consolidate_route_intersections_2d(a,b,[e for e in raw if e.kind=="cross"])
            except Exception as exc:
                errors.append(dict(pair=pair,reason=repr(exc)))
                continue
            assert raw==before
            raw_cross_clusters+=len(cross_only)
            duplicate_cross_removed+=sum(e.kind=="cross" for e in raw)-len(cross_only)
            raw_touch_to_cross+=sum(e.kind=="cross" for e in physical)-sum(e.kind=="cross" for e in cross_only)
            add_stats(physical_stats,physical)
            add_stats(groups[group]["physical"],physical)
            for e in physical:
                sink.write(json.dumps(asdict(e),sort_keys=True)+"\n")
            if pair in targets:
                midpoint.append(dict(pair=pair,raw=[asdict(e) for e in raw],
                                     physical=[asdict(e) for e in physical]))
            if raw_stats["pair_count"]%30000==0:
                print("pairs",raw_stats["pair_count"],"seconds",round(perf_counter()-loop,2),flush=True)
    elapsed=perf_counter()-loop
    unchanged=(ws==saved_ws and (preps,assignments)==saved_allocation and routes==saved_routes
               and hashes==[sha256(p.read_bytes()).hexdigest() for p in (fiberboard,snapshot)])
    result=dict(raw=raw_stats,physical=physical_stats,groups=groups,midpoint=midpoint,
                raw_cross_coordinate_clusters=raw_cross_clusters,
                duplicate_raw_cross_removed=duplicate_cross_removed,
                additional_physical_cross_from_raw_touch=raw_touch_to_cross,
                errors=errors,inputs_unchanged=unchanged,pair_loop_seconds=elapsed,
                total_seconds=perf_counter()-started,source_sha256=hashes,
                source_paths=[str(fiberboard),str(snapshot)],
                allocator_assigned=454,allocator_unsupported=58,geometry=512)
    (output/"step_8_5_legacy_512_physical_summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in ("midpoint","source_paths")},indent=2),flush=True)
    print("MIDPOINT",json.dumps([dict(pair=m["pair"],physical=m["physical"]) for m in midpoint]),flush=True)
    assert not errors and unchanged
    assert raw_stats["pair_count"]==physical_stats["pair_count"]==130816
    assert [raw_stats[k+"_events"] for k in ("cross","touch","overlap")]==[55932,12,0]
    assert len(midpoint)==3
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fiberboard",type=Path)
    parser.add_argument("snapshot",type=Path)
    args=parser.parse_args()
    validate(args.fiberboard,args.snapshot,Path(__file__).resolve().parents[1]/"outputs")


if __name__=="__main__":
    main()
