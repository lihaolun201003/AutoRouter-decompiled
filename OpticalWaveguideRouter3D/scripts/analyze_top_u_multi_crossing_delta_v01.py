"""Step J differential audit using only previously saved events and geometry."""
from pathlib import Path
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
from itertools import combinations
from math import degrees,sin,radians
from time import perf_counter
import json,re,xml.etree.ElementTree as ET
from src.models import Point2D
from src.physical_intersections import PhysicalRouteIntersection
from src.multi_crossing import build_crossing_pair_map,build_crossing_graph,enumerate_crossing_triangles,classify_multi_crossing,triplet_composition
from src.multi_crossing_delta import *
from src.loss_analysis import statistics

def read(path):return json.loads(path.read_text())
def rows(path):
 with path.open() as stream:return [json.loads(x) for x in stream]
def digest(path):return sha256(path.read_bytes()).hexdigest()
def pairmap(path):
 items=[]
 for e in rows(path):
  e["point"]=Point2D(**e["point"]) if e["point"] is not None else None
  items.append(PhysicalRouteIntersection(**e))
 return build_crossing_pair_map(items)
def eligible(triplet,pairs):
 return all(len(pairs.get(k,[]))==1 for k in combinations(triplet,2))
def candidate(triplet,pairs):
 return all(k in pairs for k in combinations(triplet,2))
def evaluate(triplet,pairs):
 if not candidate(triplet,pairs):return dict(route_ids=triplet,classification="not_graph_candidate")
 result=asdict(classify_multi_crossing(triplet,pairs))
 if result["side_lengths_mm"] is not None:
  result["crossing_angles_deg"]=[degrees(pairs[k][0].crossing_angle_rad) for k in combinations(triplet,2)]
  result.update(severity(result))
 return result

def main():
 root=Path(__file__).resolve().parents[1];out=root/"outputs"
 newnames={"step_8_5_top_u_multi_crossing_delta_summary.json","step_8_5_top_u_multi_crossing_added.jsonl",
  "step_8_5_top_u_multi_crossing_removed.jsonl","step_8_5_top_u_multi_crossing_examples.json",
  "step_8_5_top_u_reverse_multi_crossings.jsonl"}
 protected=[p for folder in ("src","outputs") for p in (root/folder).rglob("*") if p.is_file() and p.name not in newnames]
 before={str(p):digest(p) for p in protected}
 start=perf_counter()
 ab=read(out/"step_8_5_top_u_order_ab_summary.json")
 f=read(out/"step_8_5_legacy_512_loss_summary.json")
 assert digest(out/"step_8_5_legacy_512_physical_events.jsonl")==f["physical_events_sha256"]==ab["physical_source_sha256"]
 control=pairmap(out/"step_8_5_legacy_512_physical_events.jsonl")
 variant_path=out/"step_8_5_top_u_reverse_physical_events.jsonl"
 variant=pairmap(variant_path)
 assert sum(map(len,control.values()))==55935 and sum(map(len,variant.values()))==52129
 assert len(control)==49502 and len(variant)==47599
 assert all(ab["isolation"].values()) and ab["prior_outputs_unchanged"]
 plot=read(out/"step_8_5_legacy_512_plot_geometry.json")["routes"]
 special={r["id"] for r in plot if r["special"]}
 top={r["id"] for r in plot if not r["special"] and r["segments"][0]["kind"]=="line"
      and r["segments"][0]["y1"]==150 and r["segments"][-1]["kind"]=="line" and r["segments"][-1]["y2"]==150}
 assert len(top)==112 and len(special)==58
 c_multi={canonical_triplet(r["route_ids"]):r for r in rows(out/"step_8_5_legacy_512_multi_crossings.jsonl")}
 assert len(c_multi)==318
 # Validate saved Control detections with unchanged criterion and current input.
 for ids,saved in c_multi.items():
  check=evaluate(ids,control)
  assert check["classification"]=="multi_waveguide_crossing"
  assert all(abs(a-b)<1e-12 for a,b in zip(saved["side_lengths_mm"],check["side_lengths_mm"]))
 c_candidates=c_eligible=graph_stable=eligible_stable=0
 for t in enumerate_crossing_triangles(build_crossing_graph(control)):
  c_candidates+=1
  graph_stable+=candidate(t,variant)
  if eligible(t,control):
   c_eligible+=1
   eligible_stable+=eligible(t,variant)
 print("CONTROL graph/eligible set membership checked",flush=True)
 v_candidates=v_eligible=0;v_multi={};v_boundary=0
 for t in enumerate_crossing_triangles(build_crossing_graph(variant)):
  v_candidates+=1
  result=classify_multi_crossing(t,variant)
  if result.classification!="outside_legacy_single_cross_assumption":v_eligible+=1
  v_boundary+=result.classification=="boundary"
  if result.classification=="multi_waveguide_crossing":v_multi[t]=evaluate(t,variant)
 assert (c_candidates,c_eligible,v_candidates,v_eligible)==(2063548,1222071,1835220,1222071)
 assert len(v_multi)==345 and v_boundary==2
 difference=triplet_set_diff(c_multi,v_multi)
 n={k:len(v) for k,v in difference.items()}
 assert n["stable"]+n["removed"]==318 and n["stable"]+n["added"]==345 and n["added"]-n["removed"]==27
 check_top_u_invariant(difference,top)
 # Assignment metadata is read from stored H records and Variant SVG geometry;
 # do not invoke allocator or rebuild routes.
 control_assignments={}
 for r in rows(out/"step_8_5_legacy_512_double_cross_pairs.jsonl"):
  for name in ("metadata_a","metadata_b"):
   a=r[name]["assignment"];control_assignments[a["waveguide_id"]]=a
 tree=ET.parse(out/"step_8_5_top_u_reverse_variant.svg")
 variant_assignments={}
 ns={"s":"http://www.w3.org/2000/svg"}
 for group in tree.findall(".//s:g",ns):
  key=group.get("id","")
  if not key.startswith("route-"):continue
  i=int(key[6:])
  if i in special:
   variant_assignments[i]=dict(status="unsupported_geometry",track_index=None,track_y=None)
   continue
  arc=next(p.get("d") for p in group.findall("s:path",ns) if " A " in p.get("d",""))
  # First arc follows the initial vertical line; its end lies on the common track.
  tokens=arc.split();y=(880-float(tokens[-1]))/5
  index=round((y-5.025)/.175)
  assert abs(y-(5.025+.175*index))<1e-8
  variant_assignments[i]=dict(status="assigned",track_index=index,track_y=y,
                             source="derived from existing Variant SVG first-arc endpoint")
 stats={};details={}
 for name,ids_list in difference.items():
  items=[v_multi[t] if name!="removed" else c_multi[t] for t in ids_list]
  nt=Counter(sum(i in top for i in t) for t in ids_list)
  composition=Counter(triplet_composition(t,special) for t in ids_list)
  burden=Counter(i for t in ids_list for i in t if i in top)
  stats[name]=dict(count=len(items),top_u_counts={str(k):nt[k] for k in range(4)},
    composition=dict(composition),descriptive=summarize_records(items),
    top20_top_u=[dict(waveguide_id=i,count=v) for i,v in sorted(burden.items(),key=lambda x:(-x[1],x[0]))[:20]])
  if name in ("added","removed"):
   opposite=control if name=="added" else variant
   provenance=Counter()
   items_out=[]
   for t in ids_list:
    other=evaluate(t,opposite)
    label=("not_graph_candidate" if other["classification"]=="not_graph_candidate" else
           "not_eligible" if other["classification"]=="outside_legacy_single_cross_assumption" else "eligible_not_detected")
    provenance[label]+=1
    items_out.append(dict(route_ids=t,control=evaluate(t,control),variant=evaluate(t,variant),
        contains_top_u=[i for i in t if i in top],opposite_state=label,
        pair_counts=[dict(route_ids=k,control=len(control.get(k,[])),variant=len(variant.get(k,[]))) for k in combinations(t,2)]))
   stats[name]["opposite_provenance"]=dict(provenance)
   details[name]=items_out
 deltas=[margin_delta(c_multi[t],v_multi[t]) for t in difference["stable"]]
 stable_changes=Counter(d["change"] for d in deltas)
 stable_summary=dict(counts={k:stable_changes[k] for k in ("improved","worsened","unchanged")},
                     delta=statistics([d["delta"] for d in deltas]),
                     control_descriptive=summarize_records([c_multi[t] for t in difference["stable"]]),
                     variant_descriptive=summarize_records([v_multi[t] for t in difference["stable"]]))
 # Descriptive margin bins only; these do not affect criterion or classification.
 for name,source in (("added",v_multi),("removed",c_multi)):
  margins=[severity(source[t])["second_shortest_margin_mm"] for t in difference[name]]
  stats[name]["margin_bins_mm"]={
    "(0,.001]":sum(0<x<=.001 for x in margins),
    "(.001,.01]":sum(.001<x<=.01 for x in margins),
    "(.01,.05]":sum(.01<x<=.05 for x in margins),
    ">.05":sum(x>.05 for x in margins)}
 examples={}
 def select(t,reason):
  if t in examples:examples[t]["reasons"].append(reason)
  elif len(examples)<12:
   examples[t]=dict(route_ids=t,reasons=[reason],control=evaluate(t,control),variant=evaluate(t,variant),
     top_u_members=[i for i in t if i in top],
     assignments=[dict(waveguide_id=i,control=control_assignments.get(i),
                       variant=variant_assignments[i]) for i in t])
 for name,source in (("added",v_multi),("removed",c_multi)):
  ordered=sorted(difference[name],key=lambda t:(severity(source[t])["second_shortest_margin_mm"],t))
  for t in ordered[:2]:select(t,name+":near threshold")
  for t in ordered[-2:]:select(t,name+":deepest margin")
 for change in ("improved","worsened"):
  candidates=[t for t in difference["stable"] if margin_delta(c_multi[t],v_multi[t])["change"]==change]
  candidates.sort(key=lambda t:margin_delta(c_multi[t],v_multi[t])["delta"],reverse=change=="worsened")
  for t in candidates[:2]:select(t,"stable:"+change)
 for ex in examples.values():assert all(a["control"] is not None for a in ex["assignments"])
 for name,items in (("added",details["added"]),("removed",details["removed"])):
  with (out/f"step_8_5_top_u_multi_crossing_{name}.jsonl").open("w",encoding="utf-8") as sink:
   for r in items:sink.write(json.dumps(r,sort_keys=True)+"\n")
 with (out/"step_8_5_top_u_reverse_multi_crossings.jsonl").open("w",encoding="utf-8") as sink:
  for t in sorted(v_multi):sink.write(json.dumps(v_multi[t],sort_keys=True)+"\n")
 (out/"step_8_5_top_u_multi_crossing_examples.json").write_text(json.dumps(list(examples.values()),indent=2),encoding="utf-8")
 unchanged=before=={str(p):digest(p) for p in protected}
 assert unchanged
 summary=dict(criterion=dict(spacing_mm=.125,tol_mm=1e-9),counts=n,net_change=27,
  graph_set_diff=dict(stable=graph_stable,removed=c_candidates-graph_stable,added=v_candidates-graph_stable),
  eligible_set_diff=dict(stable=eligible_stable,removed=c_eligible-eligible_stable,added=v_eligible-eligible_stable),
  groups=stats,stable_severity=stable_summary,no_top_u_invariant=True,prior_files_unchanged=unchanged,
  runtime_seconds=perf_counter()-start,examples_count=len(examples),
  source_hashes=dict(control_physical=digest(out/"step_8_5_legacy_512_physical_events.jsonl"),
                    variant_physical=digest(variant_path)),
  variant_source_note="Step I did not record a Variant file hash; this audit records it and checks I counts/isolation.")
 (out/"step_8_5_top_u_multi_crossing_delta_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
 print(json.dumps(summary,indent=2))
if __name__=="__main__":main()
