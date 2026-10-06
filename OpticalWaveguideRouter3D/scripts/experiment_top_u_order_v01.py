"""Controlled A/B: reverse only top-U primary x key; never replace baseline outputs."""
from pathlib import Path
from collections import Counter,defaultdict
from copy import deepcopy
from dataclasses import asdict,replace
from hashlib import sha256
from itertools import combinations
from math import degrees,atan2
from time import perf_counter
import json
from unittest.mock import patch
from src.io import load_legacy_512_snapshot
from src.models import Point2D,LineSegment2D
from src.router_2d import (TrackPolicyConfig,prepare_waveguides_2d,assign_tracks_2d,
 generate_assigned_routes_2d,_algorithmic_endpoints,build_track_grid_2d)
from src.geometry import smooth_orthogonal_route_2d,build_special_z_smoothed_route_2d,arc_segment_radius
from src.collision import find_smoothed_route_intersections_2d,find_smoothed_route_self_intersections_2d,find_route_intersections
from src.physical_intersections import consolidate_route_intersections_2d,PhysicalRouteIntersection
from src.loss_analysis import analyze_route_loss_mm,statistics,crossing_angle_statistics
from src.multi_crossing import build_crossing_pair_map,build_crossing_graph,enumerate_crossing_triangles,classify_multi_crossing
from scripts.validate_legacy_512_exact import check_route
from src.double_cross_audit import split_cross_pairs,route_pair_type,geometry_composition


def read_json(path):return json.loads(path.read_text())
def digest(path):return sha256(path.read_bytes()).hexdigest()
def read_lines(path):
 with path.open() as stream:return [json.loads(line) for line in stream]


def metrics(events,top,bottom,special):
 split=split_cross_pairs(events)
 counts=Counter(e["kind"] for e in events)
 pair_kinds=defaultdict(set)
 for e in events:pair_kinds[tuple(sorted((e["route_a_id"],e["route_b_id"])))].add(e["kind"])
 composition=Counter();types=Counter();detail=Counter()
 def category(i):
  return "topU" if i in top else "bottomU" if i in bottom else "specialZ" if i in special else "ordinaryZ"
 for a,b in split["double"]:
  composition[geometry_composition(a in special,b in special)]+=1
  types[route_pair_type(category(a),category(b))]+=1
  detail["-".join(sorted((category(a),category(b))))]+=1
 interactions={}
 for other in ("topU","bottomU","ordinaryZ","specialZ","all"):
  selected=[e for e in events if (e["route_a_id"] in top or e["route_b_id"] in top) and
     (other=="all" or sorted((category(e["route_a_id"]),category(e["route_b_id"])))==sorted(("topU",other)))]
  pairs=split_cross_pairs(selected)
  interactions["topU-"+other]=dict(cross_points=sum(e["kind"]=="cross" for e in selected),
       cross_pairs=sum(len(v) for v in pairs.values()),double_pairs=len(pairs["double"]),
       touch=sum(e["kind"]=="touch" for e in selected),overlap=sum(e["kind"]=="overlap" for e in selected))
 return dict(cross_points=counts["cross"],cross_pairs=sum("cross" in v for v in pair_kinds.values()),
     touch=counts["touch"],overlap=counts["overlap"],
     touch_pairs=sum("touch" in v for v in pair_kinds.values()),overlap_pairs=sum("overlap" in v for v in pair_kinds.values()),
     double_pairs=len(split["double"]),higher_pairs=len(split["higher"]),
     composition={k:composition[k] for k in ("ordinary-ordinary","ordinary-special","special-special")},
     route_types={k:types[k] for k in ("U-U","U-Z","Z-Z")},
     detailed_double={k:detail[k] for k in ("topU-topU","bottomU-bottomU","bottomU-topU",
        "ordinaryZ-topU","specialZ-topU","ordinaryZ-ordinaryZ","ordinaryZ-specialZ","specialZ-specialZ")},
     top_interactions=interactions),split


def make_svg(routes,special,path):
 parts=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 980" width="1000" height="980">',
 '<rect width="1000" height="980" fill="white"/>',
 '<text x="70" y="32" font-family="Arial" font-size="21">Experimental top-U primary reversal (not baseline)</text>',
 '<text x="70" y="58" font-family="Arial" font-size="15">Blue: ordinary | Orange: independent special-Z | equal scale, mm</text>']
 def xy(p):return 70+5*p.x,880-5*p.y
 for route in routes:
  color="#dd651b" if route.waveguide_id in special else "#235fb4"
  parts.append(f'<g id="route-{route.waveguide_id}" stroke="{color}" stroke-width="0.7" stroke-opacity="0.6" fill="none">')
  for s in route.segments:
   x1,y1=xy(s.start);x2,y2=xy(s.end)
   if isinstance(s,LineSegment2D):d=f"M {x1} {y1} L {x2} {y2}"
   else:
    radius=arc_segment_radius(s)*5
    d=f"M {x1} {y1} A {radius} {radius} 0 0 {int(s.sweep_rad<0)} {x2} {y2}"
   parts.append(f'<path d="{d}"/>')
  parts.append("</g>")
 parts.append('<g font-family="Arial" font-size="16" fill="#222">')
 for i in range(0,151,25):
  parts.append(f'<text x="25" y="{885-5*i}">{i}</text><text x="{70+5*i}" y="915">{i}</text>')
 parts.append('<text x="840" y="915">X (mm)</text><text x="15" y="100">Y (mm)</text></g></svg>')
 path.write_text("\n".join(parts),encoding="utf-8")


def main():
 root=Path(__file__).resolve().parents[1];out=root/"outputs"
 protected=[p for p in out.rglob("*") if p.is_file() and not p.name.startswith("step_8_5_top_u_")]
 hashes={str(p):digest(p) for p in protected}
 started=perf_counter();timing={}
 base=next(root.parent.glob("*/AutoRouter/fiberBoard512.xlsx")).parent
 source=[base/"fiberBoard512.xlsx",base/"fiberBoard0data.xlsx"]
 f=read_json(out/"step_8_5_legacy_512_loss_summary.json")
 g=read_json(out/"step_8_5_legacy_512_multi_crossing_summary.json")
 assert [digest(p) for p in source]==f["source_hashes"]
 assert digest(out/"step_8_5_legacy_512_physical_events.jsonl")==f["physical_events_sha256"]==g["physical_events_sha256"]
 ws=load_legacy_512_snapshot(*source);saved_ws=deepcopy(ws)
 preps=prepare_waveguides_2d(ws,150,0)
 cfg=TrackPolicyConfig(150,.05,.125,5)
 variant_cfg=replace(cfg,top_u_primary_order="descending")
 control_a=assign_tracks_2d(ws,preps,cfg)
 saved_control_a=deepcopy(control_a)
 top={p.waveguide_id for p in preps if p.route_type=="u" and p.side=="top"}
 bottom={p.waveguide_id for p in preps if p.route_type=="u" and p.side=="bottom"}
 special={a.waveguide_id for a in control_a if a.status=="unsupported_geometry"}
 ww={w.id:w for w in ws};pp={p.waveguide_id:p for p in preps}
 def build(assignments):
  skeleton=generate_assigned_routes_2d(ws,preps,assignments,top_y=150,bottom_y=0)
  curves=[smooth_orthogonal_route_2d(r,5) for r in skeleton]
  curves += [build_special_z_smoothed_route_2d(i,ww[i].start_port.position,ww[i].end_port.position,5) for i in sorted(special)]
  return {r.waveguide_id:r for r in skeleton},{r.waveguide_id:r for r in curves}
 control_s,control_r=build(control_a)
 control_events=read_lines(out/"step_8_5_legacy_512_physical_events.jsonl")
 # Confirm default geometry reproduces stored per-route lengths/losses.
 old_losses={r["waveguide_id"]:r for r in f["per_waveguide"]}
 for i,r in control_r.items():
  loss=analyze_route_loss_mm(r)
  assert all(abs(loss[k]-old_losses[i][k])<1e-9 for k in
     ("total_length_mm","propagation_loss_db","bend_loss_db","known_non_crossing_loss_db"))
 timing["control_load_rebuild_seconds"]=perf_counter()-started
 t=perf_counter()
 variant_a=assign_tracks_2d(ws,preps,variant_cfg)
 ca={a.waveguide_id:a for a in control_a};va={a.waveguide_id:a for a in variant_a}
 isolation=dict(non_top_assignments_unchanged=all(ca[i]==va[i] for i in ca if i not in top),
  top_assigned_ids_unchanged={i for i in top if ca[i].status=="assigned"}=={i for i in top if va[i].status=="assigned"},
  top_track_pool_unchanged={ca[i].track_index for i in top}=={va[i].track_index for i in top},
  grid_unchanged=build_track_grid_2d(cfg)==build_track_grid_2d(variant_cfg))
 if not all(isolation.values()):
  (out/"step_8_5_top_u_order_ab_summary.json").write_text(json.dumps(dict(isolation=isolation,stopped=True),indent=2))
  raise ValueError("Isolation failed: stopped before geometry/collision.")
 assert Counter(a.status for a in variant_a)=={"assigned":454,"unsupported_geometry":58}
 assert len({a.track_index for a in variant_a if a.status=="assigned"})==454
 variant_s,variant_r=build(variant_a)
 assert len(variant_s)==454 and len(variant_r)==512
 isolation["non_top_geometry_unchanged"]=all(variant_r[i]==control_r[i] for i in control_r if i not in top)
 assert isolation["non_top_geometry_unchanged"]
 saved_control_r=deepcopy(control_r);saved_variant_r=deepcopy(variant_r)
 # Snapshot matches default Control assignments route by route where prior H
 # records carry them, beyond aggregate agreement.
 for old in read_lines(out/"step_8_5_legacy_512_double_cross_pairs.jsonl"):
  for key in ("metadata_a","metadata_b"):
   assignment=old[key]["assignment"]
   assert asdict(ca[assignment["waveguide_id"]])==assignment
 timing["variant_allocator_geometry_seconds"]=perf_counter()-t
 t=perf_counter()
 nested=set();skeleton_counts={};nested_counts={}
 for a,b in combinations(sorted(top),2):
  aa,ab=_algorithmic_endpoints(ww[a],pp[a],1e-9)
  ba,bb=_algorithmic_endpoints(ww[b],pp[b],1e-9)
  if (aa.position.x-ba.position.x)*(ab.position.x-bb.position.x)<0:nested.add((a,b))
 for label,sk in (("control",control_s),("variant",variant_s)):
  doubles=set()
  for a,b in combinations(sorted(top),2):
   raw=find_route_intersections(sk[a],sk[b])
   if sum(e.kind=="cross" for e in raw)==2:doubles.add((a,b))
  skeleton_counts[label]=len(doubles);nested_counts[label]=len(doubles&nested)
 timing["skeleton_diagnostic_seconds"]=perf_counter()-t
 print("ISOLATION",isolation,"SKELETON",skeleton_counts,flush=True)
 t=perf_counter();self_counts=Counter();geometry_errors=[]
 for i,r in variant_r.items():
  errors=check_route(r,ww[i])
  if errors:geometry_errors.append(dict(id=i,errors=errors))
  self_counts.update(e.kind for e in find_smoothed_route_self_intersections_2d(r))
 assert not geometry_errors and not sum(self_counts.values())
 timing["geometry_self_seconds"]=perf_counter()-t
 physical=[];pair_count=0;collision_time=0.;consolidation_time=0.
 raw_counts=Counter()
 with (out/"step_8_5_top_u_reverse_physical_events.jsonl").open("w",encoding="utf-8") as sink:
  for a,b in combinations(variant_r.values(),2):
   t=perf_counter();raw=find_smoothed_route_intersections_2d(a,b);collision_time+=perf_counter()-t
   raw_counts.update(e.kind for e in raw)
   t=perf_counter();events=consolidate_route_intersections_2d(a,b,raw);consolidation_time+=perf_counter()-t
   for e in events:
    d=asdict(e);physical.append(d);sink.write(json.dumps(d)+"\n")
   pair_count+=1
   if pair_count%30000==0:print("VARIANT PAIRS",pair_count,flush=True)
 assert pair_count==130816
 timing["variant_raw_collision_seconds"]=collision_time
 timing["physical_consolidation_seconds"]=consolidation_time
 t=perf_counter()
 control_metrics,control_split=metrics(control_events,top,bottom,special)
 variant_metrics,variant_split=metrics(physical,top,bottom,special)
 assert control_metrics["double_pairs"]==6433 and control_metrics["detailed_double"]["topU-topU"]==1903
 assert control_metrics["cross_points"]==55935 and control_metrics["cross_pairs"]==49502
 with (out/"step_8_5_top_u_reverse_double_cross_pairs.jsonl").open("w",encoding="utf-8") as sink:
  for pair,events in variant_split["double"].items():sink.write(json.dumps(dict(route_ids=pair,crossings=events))+"\n")
 nested_physical=dict(pair_count=len(nested),
   control_double=sum(p in control_split["double"] for p in nested),
   variant_double=sum(p in variant_split["double"] for p in nested))
 timing["double_cross_analysis_seconds"]=perf_counter()-t
 t=perf_counter()
 objects=[]
 for e in physical:
  copy=dict(e);copy["point"]=Point2D(**e["point"]) if e["point"] is not None else None
  objects.append(PhysicalRouteIntersection(**copy))
 pairs=build_crossing_pair_map(objects);graph=build_crossing_graph(pairs);multi=Counter()
 for triplet in enumerate_crossing_triangles(graph):
  multi[classify_multi_crossing(triplet,pairs,.125,1e-9).classification]+=1
 timing["multi_crossing_seconds"]=perf_counter()-t
 variant_multi=dict(candidates=sum(multi.values()),legacy_eligible=sum(multi.values())-multi["outside_legacy_single_cross_assumption"],
   outside=multi["outside_legacy_single_cross_assumption"],detected=multi["multi_waveguide_crossing"],
   boundary=multi["boundary"],non_multi=multi["not_multi_waveguide_crossing"])
 t=perf_counter()
 with patch("src.loss.crossing_loss",side_effect=AssertionError("Forbidden crossing loss")) as forbidden:
  losses=[analyze_route_loss_mm(r) for r in variant_r.values()]
  angles=crossing_angle_statistics(physical,list(variant_r))
  assert not forbidden.called
 assert all(abs(r["bend_loss_db"]-4.78)<1e-9 for r in losses if r["waveguide_id"] not in special)
 fields=("total_length_mm","propagation_loss_db","bend_loss_db","known_non_crossing_loss_db")
 loss_stats={k:statistics([r[k] for r in losses]) for k in fields}
 angle_stats=angles["degrees"]
 angle_stats["below_20_count"]=sum(e["kind"]=="cross" and degrees(e["crossing_angle_rad"])<20 for e in physical)
 control_angles=dict(f["crossing_angles"]["degrees"])
 control_angles["below_20_count"]=sum(b["count"] for b in f["crossing_angles"]["histogram"] if b["upper_deg"]<=20)
 timing["loss_angle_seconds"]=perf_counter()-t
 ranges={}
 for name in ("topU","bottomU","top_to_bottomZ","bottom_to_topZ"):
  members=[]
  for w in ws:
   if w.id in special:continue
   aa,bb=_algorithmic_endpoints(w,pp[w.id],1e-9)
   group="topU" if w.id in top else "bottomU" if w.id in bottom else "top_to_bottomZ" if aa.position.y==150 else "bottom_to_topZ"
   if name==group:members.append(w.id)
  ranges[name]=dict(control_min=min(ca[i].track_index for i in members),control_max=max(ca[i].track_index for i in members),
    variant_min=min(va[i].track_index for i in members),variant_max=max(va[i].track_index for i in members))
 assert all(not (max(a["variant_min"],b["variant_min"])<=min(a["variant_max"],b["variant_max"])) for a,b in combinations(ranges.values(),2))
 make_svg(list(variant_r.values()),special,out/"step_8_5_top_u_reverse_variant.svg")
 assert ws==saved_ws and control_a==saved_control_a and control_r==saved_control_r and variant_r==saved_variant_r
 assert hashes=={str(p):digest(p) for p in protected}
 assert [digest(p) for p in source]==f["source_hashes"]
 timing["total_seconds"]=perf_counter()-started
 result=dict(control_config=asdict(cfg),variant_config=asdict(variant_cfg),isolation=isolation,
  invariant_counts=dict(input=512,assigned=454,unsupported=58,no_available_track=0,skeletons=454,ordinary_curves=454,special_curves=58,total=512),
  changed_top_assignments=sum(ca[i]!=va[i] for i in top),checked_pairs=pair_count,
  geometry_errors=geometry_errors,self_counts={k:self_counts[k] for k in ("cross","touch","overlap")},
  control=control_metrics,variant=variant_metrics,
  primary=dict(control=1903,variant=variant_metrics["detailed_double"]["topU-topU"],
    absolute_change=variant_metrics["detailed_double"]["topU-topU"]-1903,
    relative_change_percent=100*(variant_metrics["detailed_double"]["topU-topU"]-1903)/1903),
  skeleton_top_u_double=skeleton_counts,nested_skeleton=nested_counts,nested_physical=nested_physical,
  control_multi=dict(detected=318,boundary=2,legacy_eligible=g["legacy_eligible_triangles"],outside=g["outside_legacy_assumption_triangles"]),
  variant_multi=variant_multi,control_angles=control_angles,variant_angles=angle_stats,
  control_losses={k:f["groups"]["global"][k] for k in fields},variant_losses=loss_stats,
  variant_raw_counts=dict(raw_counts),track_ranges=ranges,runtime=timing,
  prior_outputs_unchanged=True,physical_source_sha256=digest(out/"step_8_5_legacy_512_physical_events.jsonl"))
 (out/"step_8_5_top_u_order_ab_summary.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
 print(json.dumps(result,indent=2))

if __name__=="__main__":main()
