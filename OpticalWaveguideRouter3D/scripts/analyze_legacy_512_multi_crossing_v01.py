"""Read-only legacy 512 multi-crossing audit; reuse validated physical event JSONL."""
from pathlib import Path
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
from math import degrees
from itertools import combinations
import json
from time import perf_counter
from src.models import Point2D
from src.physical_intersections import PhysicalRouteIntersection
from src.multi_crossing import (
 build_crossing_pair_map,audit_pair_multiplicity,build_crossing_graph,
 enumerate_crossing_triangles,classify_multi_crossing,triplet_composition)


def digest(path):
 return sha256(path.read_bytes()).hexdigest()


def main():
 root=Path(__file__).resolve().parents[1]
 out=root/"outputs"
 output_names={"step_8_5_legacy_512_multi_crossing_summary.json","step_8_5_legacy_512_multi_crossings.jsonl"}
 protected=[p for folder in ("src","outputs") for p in (root/folder).rglob("*")
            if p.is_file() and p.name not in output_names]
 before={str(p):digest(p) for p in protected}
 started=perf_counter()
 event_path=out/"step_8_5_legacy_512_physical_events.jsonl"
 loss=json.loads((out/"step_8_5_legacy_512_loss_summary.json").read_text())
 assert digest(event_path)==loss["physical_events_sha256"], "Physical events hash mismatch"
 assert loss["inputs_unchanged"]
 records=loss["per_waveguide"]
 ids={r["waveguide_id"] for r in records}
 special={r["waveguide_id"] for r in records if r["geometry_type"]=="special"}
 assert len(ids)==512 and len(special)==58
 assert Counter(r["allocator_status"] for r in records)=={"assigned":454,"unsupported_geometry":58}
 events=[]
 with event_path.open(encoding="utf-8") as stream:
  for line in stream:
   e=json.loads(line)
   p=e["point"]
   e["point"]=Point2D(**p) if p is not None else None
   events.append(PhysicalRouteIntersection(**e))
 assert len(events)==55935 and all(e.kind=="cross" for e in events)
 assert all(e.route_a_id in ids and e.route_b_id in ids for e in events)
 t=perf_counter()
 pairs=build_crossing_pair_map(events)
 pair_seconds=perf_counter()-t
 multiplicity=audit_pair_multiplicity(pairs)
 assert len(pairs)==49502
 t=perf_counter()
 graph=build_crossing_graph(pairs)
 graph_seconds=perf_counter()-t
 counters=Counter()
 composition=Counter()
 burden={i:0 for i in ids}
 angle_min=None
 angle_sum=0.0
 angle_count=0
 small_angle_triplets=0
 boundary_any=0
 boundary_multi=0
 outside_examples=[]
 boundary_examples=[]
 enumeration_seconds=0.0
 criterion_seconds=0.0
 saved=0
 cap=100000
 iterator=enumerate_crossing_triangles(graph)
 with (out/"step_8_5_legacy_512_multi_crossings.jsonl").open("w",encoding="utf-8") as stream:
  while True:
   t=perf_counter()
   try: triplet=next(iterator)
   except StopIteration:
    enumeration_seconds+=perf_counter()-t
    break
   enumeration_seconds+=perf_counter()-t
   t=perf_counter()
   result=classify_multi_crossing(triplet,pairs,spacing_mm=.125,tol=1e-9)
   criterion_seconds+=perf_counter()-t
   counters[result.classification]+=1
   if result.boundary_side_count:
    boundary_any+=1
    if len(boundary_examples)<20:boundary_examples.append(asdict(result))
   if result.classification=="outside_legacy_single_cross_assumption":
    if len(outside_examples)<20:
     outside_examples.append(dict(route_ids=triplet,pair_cross_counts=[
      dict(route_ids=k,count=len(pairs[k])) for k in combinations(triplet,2)]))
   elif result.classification=="multi_waveguide_crossing":
    composition[triplet_composition(triplet,special)]+=1
    if result.boundary_side_count:boundary_multi+=1
    for i in triplet:burden[i]+=1
    angles=[degrees(pairs[key][0].crossing_angle_rad) for key in combinations(triplet,2)]
    angle_min=min(angles) if angle_min is None else min(angle_min,*angles)
    angle_sum+=sum(angles)
    angle_count+=3
    small_angle_triplets+=min(angles)<20
    if saved<cap:
     record=asdict(result)
     record.update(crossing_angles_deg=angles,min_crossing_angle_deg=min(angles),
                   mean_crossing_angle_deg=sum(angles)/3,contains_below_20_deg=min(angles)<20,
                   composition=triplet_composition(triplet,special))
     stream.write(json.dumps(record,sort_keys=True)+"\n")
     saved+=1
   n=sum(counters.values())
   if n%250000==0:print("triangles",n,"detected",counters["multi_waveguide_crossing"],flush=True)
 total=sum(counters.values())
 eligible=total-counters["outside_legacy_single_cross_assumption"]
 assert sum(burden.values())==3*counters["multi_waveguide_crossing"]
 assert sum(composition.values())==counters["multi_waveguide_crossing"]
 unchanged=before=={str(p):digest(p) for p in protected}
 assert unchanged
 result=dict(
  configuration=dict(spacing_mm=.125,tol_mm=1e-9,track_pitch_mm_not_used=.175,
                     criterion="at least two lengths < spacing - tol"),
  physical_cross_count=len(events),multiplicity=multiplicity,
  graph_nodes_with_cross=len(graph),graph_triangle_candidates=total,
  legacy_eligible_triangles=eligible,
  outside_legacy_assumption_triangles=counters["outside_legacy_single_cross_assumption"],
  multi_waveguide_crossing_count=counters["multi_waveguide_crossing"],
  non_multi_crossing_triangle_count=counters["not_multi_waveguide_crossing"],
  boundary_triangle_count=counters["boundary"],
  triangles_with_any_boundary_side=boundary_any,multi_with_boundary_side=boundary_multi,
  composition={k:composition[k] for k in ("ordinary/ordinary/ordinary","ordinary/ordinary/special",
                                        "ordinary/special/special","special/special/special")},
  per_waveguide=[dict(waveguide_id=i,special=i in special,participating_multi_crossing_count=burden[i]) for i in sorted(ids)],
  top20_waveguides=[dict(waveguide_id=i,special=i in special,participating_multi_crossing_count=v)
                    for i,v in sorted(burden.items(),key=lambda x:(-x[1],x[0]))[:20]],
  crossing_angle_auxiliary=dict(min_deg=angle_min,mean_deg=angle_sum/angle_count if angle_count else None,
      angle_occurrences=angle_count,triplets_with_below_20_deg=small_angle_triplets),
  runtime=dict(pair_map_seconds=pair_seconds,graph_seconds=graph_seconds,
               triangle_enumeration_seconds=enumeration_seconds,criterion_seconds=criterion_seconds,
               total_seconds=perf_counter()-started),
  jsonl_records=saved,jsonl_truncated=saved<counters["multi_waveguide_crossing"],
  outside_examples=outside_examples,boundary_examples=boundary_examples,
  physical_events_sha256=digest(event_path),protected_files_unchanged=unchanged,
  allocator_counts=dict(assigned=454,unsupported_geometry=58))
 (out/"step_8_5_legacy_512_multi_crossing_summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
 print(json.dumps({k:v for k,v in result.items() if k not in
                   ("per_waveguide","outside_examples","boundary_examples")},indent=2))


if __name__=="__main__":
 main()
