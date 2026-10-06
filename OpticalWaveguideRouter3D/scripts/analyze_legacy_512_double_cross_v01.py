"""Step H read-only double-cross topology audit."""
from pathlib import Path
from collections import Counter,defaultdict
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
from itertools import combinations
from math import degrees,hypot
from time import perf_counter
import json
from src.io import load_legacy_512_snapshot
from src.router_2d import (prepare_waveguides_2d,assign_tracks_2d,TrackPolicyConfig,
 generate_assigned_routes_2d,_algorithmic_endpoints)
from src.geometry import smooth_orthogonal_route_2d,build_special_z_smoothed_route_2d
from src.models import Point2D
from src.collision import find_route_intersections
from src.loss_analysis import statistics
from src.double_cross_audit import *


def main():
 root=Path(__file__).resolve().parents[1];out=root/"outputs"
 new={"step_8_5_legacy_512_double_cross_summary.json","step_8_5_legacy_512_double_cross_pairs.jsonl",
      "step_8_5_double_cross_examples.json"}
 protected=[p for folder in ("src","outputs") for p in (root/folder).rglob("*") if p.is_file() and p.name not in new]
 hashes={str(p):sha256(p.read_bytes()).hexdigest() for p in protected}
 started=perf_counter()
 event_file=out/"step_8_5_legacy_512_physical_events.jsonl"
 digest=sha256(event_file.read_bytes()).hexdigest()
 f=json.loads((out/"step_8_5_legacy_512_loss_summary.json").read_text())
 g=json.loads((out/"step_8_5_legacy_512_multi_crossing_summary.json").read_text())
 assert digest==f["physical_events_sha256"]==g["physical_events_sha256"]
 with event_file.open() as stream:events=[json.loads(line) for line in stream]
 split=split_cross_pairs(events);double=split["double"]
 assert len(events)==55935 and len(double)==6433 and len(split["single"])==43069 and not split["higher"]
 base=next(root.parent.glob("*/AutoRouter/fiberBoard512.xlsx")).parent
 sources=[base/"fiberBoard512.xlsx",base/"fiberBoard0data.xlsx"]
 source_hashes=[sha256(p.read_bytes()).hexdigest() for p in sources]
 assert source_hashes==f["source_hashes"]
 ws=load_legacy_512_snapshot(*sources);saved_ws=deepcopy(ws)
 preps=prepare_waveguides_2d(ws,150,0)
 assignments=assign_tracks_2d(ws,preps,TrackPolicyConfig(150,.05,.125,5))
 saved_assignments=deepcopy(assignments)
 assert Counter(a.status for a in assignments)=={"assigned":454,"unsupported_geometry":58}
 aa={a.waveguide_id:a for a in assignments}
 pp={p.waveguide_id:p for p in preps}
 special={a.waveguide_id for a in assignments if a.status=="unsupported_geometry"}
 skeletons={r.waveguide_id:r for r in generate_assigned_routes_2d(ws,preps,assignments,top_y=150,bottom_y=0)}
 curves={i:smooth_orthogonal_route_2d(r,5) for i,r in skeletons.items()}
 ww={w.id:w for w in ws}
 for i in special:curves[i]=build_special_z_smoothed_route_2d(i,ww[i].start_port.position,ww[i].end_port.position,5)
 saved_curves=deepcopy(curves)
 metadata={}
 group_items=defaultdict(list)
 for w in ws:
  p=pp[w.id]
  alg_a,alg_b=_algorithmic_endpoints(w,p,1e-9)
  group=("topU" if p.side=="top" else "bottomU") if p.route_type=="u" else (
       "top_to_bottomZ" if alg_a.position.y==150 else "bottom_to_topZ")
  actual=("topU" if p.side=="top" else "bottomU") if p.route_type=="u" else (
       "top_to_bottomZ" if w.start_port.position.y==150 else "bottom_to_topZ")
  metadata[w.id]=dict(route_type=actual,algorithmic_group=group,special=w.id in special,
    algorithmic_start_x=alg_a.position.x,algorithmic_end_x=alg_b.position.x,
    preparation=asdict(p),assignment=asdict(aa[w.id]))
  if w.id not in special:
   key=(alg_a.position.x,alg_b.position.x,alg_a.pmt_id,alg_b.pmt_id,w.id)
   group_items[group].append((key,w.id))
 ranks={}
 ranges={}
 for group,items in group_items.items():
  order=sorted(items)
  for rank,(_,i) in enumerate(order):ranks[i]=rank
  indices=[aa[i].track_index for _,i in order]
  ys=[aa[i].track_y for _,i in order]
  ranges[group]=dict(min_y=min(ys),max_y=max(ys),min_index=min(indices),max_index=max(indices),count=len(indices))
 assert len({a.track_index for a in assignments if a.status=="assigned"})==454
 raw_by_pair=defaultdict(list)
 with (out/"step_8_5_legacy_512_exact_events.jsonl").open() as stream:
  for line in stream:
   e=json.loads(line);key=tuple(sorted((e["route_id_a"],e["route_id_b"])))
   if key in double:raw_by_pair[key].append(e)
 result_rows=[]
 # Explicit zeros keep summary categories complete.

 comp=Counter();types=Counter();detailed=Counter();topologies=Counter();skeleton_stats=Counter()
 progress_bins=Counter();dist_bins=Counter();track_bins=Counter()
 burden=Counter();track_diffs=[];distances=[]
 ordering=Counter();group_pair_counts=Counter()
 bend_cross_count=0;bend_pair_count=0
 for pair,physical in double.items():
  a,b=pair;ma,mb=metadata[a],metadata[b]
  composition=geometry_composition(a in special,b in special)
  comp[composition]+=1
  typ=route_pair_type(ma["route_type"],mb["route_type"]);types[typ]+=1
  detail="-".join(sorted(("specialZ" if a in special else ma["route_type"],
                          "specialZ" if b in special else mb["route_type"])))
  detailed[detail]+=1
  points=sorted(physical,key=lambda e:(e["point"]["x"],e["point"]["y"]))
  audits=[]
  for e in points:
   p=Point2D(**e["point"])
   matched=[raw for raw in raw_by_pair[pair] if raw["point"] is not None and
            hypot(raw["point"]["x"]-p.x,raw["point"]["y"]-p.y)<=1e-9]
   assert matched,(pair,"no raw provenance")
   indices_a=set();indices_b=set()
   for raw in matched:
    if raw["route_id_a"]==a:
     indices_a.add(raw["segment_index_a"]);indices_b.add(raw["segment_index_b"])
    else:
     indices_a.add(raw["segment_index_b"]);indices_b.add(raw["segment_index_a"])
   sa={type(curves[a].segments[i]).__name__ for i in indices_a}
   sb={type(curves[b].segments[i]).__name__ for i in indices_b}
   topology=segment_topology(sa,sb)
   pa=[normalized_progress(curves[a],p,i) for i in indices_a]
   pb=[normalized_progress(curves[b],p,i) for i in indices_b]
   assert max(pa)-min(pa)<1e-9 and max(pb)-min(pb)<1e-9
   for v in (pa[0],pb[0]):
    label=("[0,.1)" if v<.1 else "[.1,.25)" if v<.25 else "[.25,.75)" if v<.75 else
           "[.75,.9)" if v<.9 else "[.9,1]")
    progress_bins[label]+=1
   audits.append(dict(point=e["point"],angle_deg=degrees(e["crossing_angle_rad"]),
     topology=topology,segment_indices_a=sorted(indices_a),segment_indices_b=sorted(indices_b),
     progress_a=pa[0],progress_b=pb[0],raw_event_count=len(matched)))
  topo=" + ".join(sorted(x["topology"] for x in audits));topologies[topo]+=1
  n_bend=sum("Arc" in x["topology"] for x in audits)
  bend_cross_count+=n_bend;bend_pair_count+=n_bend>0
  d=hypot(points[0]["point"]["x"]-points[1]["point"]["x"],points[0]["point"]["y"]-points[1]["point"]["y"])
  distances.append(d)
  dist_bins["<.125" if d<.125 else "[.125,.175)" if d<.175 else "[.175,1)" if d<1 else "[1,5]" if d<=5 else ">5"]+=1
  sk=None;diff=None;relation=None
  if composition=="ordinary-ordinary":
   raw_skeleton=find_route_intersections(skeletons[a],skeletons[b])
   counts=Counter(e.kind for e in raw_skeleton)
   label=skeleton_comparison(counts["cross"],counts["touch"],counts["overlap"]);skeleton_stats[label]+=1
   sk=dict(classification=label,raw_kind_counts=dict(counts),
           events=[asdict(e) for e in raw_skeleton])
   diff=track_difference(aa[a].track_index,aa[b].track_index);track_diffs.append(diff)
   track_bins["0" if diff==0 else "1" if diff==1 else "2-5" if diff<=5 else "6-20" if diff<=20 else ">20"]+=1
   same=ma["algorithmic_group"]==mb["algorithmic_group"]
   ordering["same_group" if same else "different_group"]+=1
   group_pair_counts[" / ".join(sorted((ma["algorithmic_group"],mb["algorithmic_group"])))]+=1
   if same:
    rank_delta=ranks[a]-ranks[b]
    expected=1 if ma["algorithmic_group"]=="bottomU" else -1
    inversion=(aa[a].track_index-aa[b].track_index)*rank_delta*expected<0
    endpoint_inversion=(ma["algorithmic_start_x"]-mb["algorithmic_start_x"])*(ma["algorithmic_end_x"]-mb["algorithmic_end_x"])<0
    ordering["scan_order_inversion"]+=inversion
    ordering["endpoint_order_inversion_same_group"]+=endpoint_inversion
    relation=dict(scan_order_inversion=inversion,endpoint_order_inversion=endpoint_inversion,
                  rank_a=ranks[a],rank_b=ranks[b])
  burden.update(pair)
  result_rows.append(dict(route_a_id=a,route_b_id=b,point_1=audits[0]["point"],point_2=audits[1]["point"],
    distance_between_crosses_mm=d,angle_1_deg=audits[0]["angle_deg"],angle_2_deg=audits[1]["angle_deg"],
    composition=composition,route_pair_type=typ,detailed_type=detail,topology_combination=topo,
    crossings=audits,skeleton_comparison=sk,track_index_difference=diff,ordering_relation=relation,
    metadata_a=ma,metadata_b=mb))
 output=out/"step_8_5_legacy_512_double_cross_pairs.jsonl"
 with output.open("w",encoding="utf-8") as stream:
  for row in result_rows:stream.write(json.dumps(row,sort_keys=True)+"\n")
 # Deterministic diverse representatives, capped at twenty.
 chosen={}
 def select(row,reason):
  key=(row["route_a_id"],row["route_b_id"])
  if key in chosen:chosen[key]["selection_reasons"].append(reason)
  elif len(chosen)<20:chosen[key]=dict(**row,selection_reasons=[reason])
 select(min(result_rows,key=lambda r:r["distance_between_crosses_mm"]),"closest")
 select(max(result_rows,key=lambda r:r["distance_between_crosses_mm"]),"farthest")
 for field in ("route_pair_type","composition","topology_combination"):
  for value in sorted({r[field] for r in result_rows}):
   select(next(r for r in result_rows if r[field]==value),field+":"+value)
 for value in sorted(skeleton_stats):
  select(next(r for r in result_rows if r["skeleton_comparison"] and r["skeleton_comparison"]["classification"]==value),value)
 for row in result_rows:
  if len(chosen)>=20:break
  select(row,"canonical additional example")
 (out/"step_8_5_double_cross_examples.json").write_text(json.dumps(list(chosen.values()),indent=2),encoding="utf-8")
 unchanged=(saved_ws==ws and saved_assignments==assignments and curves==saved_curves
            and hashes=={str(p):sha256(p.read_bytes()).hexdigest() for p in protected}
            and source_hashes==[sha256(p.read_bytes()).hexdigest() for p in sources])
 assert unchanged
 assert sum(progress_bins.values())==6433*4
 for key in ('ordinary-ordinary','ordinary-special','special-special'):comp.setdefault(key,0)
 for key in ('U-U','U-Z','Z-Z'):types.setdefault(key,0)
 for key in ('skeleton_2_to_smooth_2','skeleton_1_to_smooth_2','skeleton_0_to_smooth_2','other'):skeleton_stats.setdefault(key,0)
 for key in ('<.125','[.125,.175)','[.175,1)','[1,5]','>5'):dist_bins.setdefault(key,0)
 for key in ('0','1','2-5','6-20','>20'):track_bins.setdefault(key,0)
 summary=dict(double_cross_pairs=len(double),physical_events_sha256=digest,
  composition={k:dict(count=v,percentage=100*v/6433) for k,v in comp.items()},
  route_types=dict(types),detailed_types=dict(detailed),segment_topologies=dict(topologies),
  bend_related_intersections=bend_cross_count,bend_related_pairs=bend_pair_count,
  distance_mm=statistics(distances),distance_bins=dict(dist_bins),progress_bins=dict(progress_bins),
  skeleton_comparison=dict(skeleton_stats),track_difference=statistics(track_diffs),track_difference_bins=dict(track_bins),
  ordering=dict(ordering),algorithmic_group_pair_counts=dict(group_pair_counts),
  category_track_ranges=ranges,category_range_overlap=category_range_overlap(ranges),
  top20_waveguides=[dict(waveguide_id=i,double_cross_pair_count=n) for i,n in sorted(burden.items(),key=lambda x:(-x[1],x[0]))[:20]],
  top20_pairs=[dict(route_a_id=r["route_a_id"],route_b_id=r["route_b_id"],
                   distance_between_crosses_mm=r["distance_between_crosses_mm"],topology=r["topology_combination"])
               for r in sorted(result_rows,key=lambda r:(-r["distance_between_crosses_mm"],r["route_a_id"],r["route_b_id"]))[:20]],
  examples_count=len(chosen),unchanged=unchanged,runtime_seconds=perf_counter()-started)
 (out/"step_8_5_legacy_512_double_cross_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
 print(json.dumps({k:v for k,v in summary.items() if k not in ("top20_pairs",)},indent=2))

if __name__=="__main__":main()
