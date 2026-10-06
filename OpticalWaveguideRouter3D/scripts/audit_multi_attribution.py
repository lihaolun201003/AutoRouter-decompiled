"""Audit saved ascending geometry and saved crossings; never run an allocator."""
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
from itertools import combinations
from math import hypot
from pathlib import Path
import argparse
import csv
import json
from xml.sax.saxutils import escape

from src.models import Point2D
from src.io import load_legacy_512_snapshot
from src.router_2d import prepare_waveguide_2d, _algorithmic_endpoints
from src.multi_crossing import build_crossing_pair_map, classify_multi_crossing
from src.physical_intersections import PhysicalRouteIntersection
from src.multi_attribution import (
    deserialize_plot, physical_endpoints, chain_ownership, primitive_attribution,
    point_on_primitive, arc_vertical_relations, pair_token, topology_signature,
    classify_paper_like, geometric_pmt_order,
)

PREFIX="step_8_5_m1_5"
BASE="step_8_5_legacy_512"


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def read_lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_csv(path, records):
    with path.open("w",encoding="utf-8-sig",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=list(records[0]))
        writer.writeheader()
        for record in records:
            writer.writerow({k:json.dumps(v,sort_keys=True) if isinstance(v,(list,dict,tuple)) else v
                             for k,v in record.items()})


def svg_start(width,height,title):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="white"/>',
            f'<text x="45" y="30" font-family="Arial" font-size="19">{escape(title)}</text>']


def scatter_svg(records):
    parts=svg_start(950,950,"Ascending baseline: 318 exact multi centroids")
    scale=5.3
    def xy(x,y): return 85+x*scale,860-y*scale
    for value in range(0,151,25):
        x,y=xy(value,value)
        parts += [f'<path d="M {x} 65 V 860 M 85 {y} H 880" fill="none" stroke="#ddd"/>',
                  f'<text x="{x}" y="884" text-anchor="middle" font-family="Arial">{value}</text>',
                  f'<text x="72" y="{y+4}" text-anchor="end" font-family="Arial">{value}</text>']
    colors={"special_related":"#ff7f0e","top_U_related":"#1f77b4","bottom_U_related":"#2ca02c","cross_side_Z":"#9467bd"}
    for r in records:
        x,y=xy(r["centroid"]["x"],r["centroid"]["y"])
        parts.append(f'<circle cx="{x}" cy="{y}" r="3.1" fill="{colors[r["spatial_group"]]}" fill-opacity=".6"><title>{r["multi_id"]}: {r["route_ids"]}</title></circle>')
    for i,(label,color) in enumerate(colors.items()):
        parts += [f'<circle cx="{85+i*215}" cy="917" r="4" fill="{color}"/>',
                  f'<text x="{95+i*215}" y="922" font-family="Arial" font-size="12">{label}</text>']
    parts += ['<text x="870" y="896" font-family="Arial">X (mm)</text>',
              '<text x="12" y="70" font-family="Arial">Y (mm)</text>','</svg>']
    return "\n".join(parts)


def case_svg(record, plot_by_id):
    parts=svg_start(1200,660,f'{record["multi_id"]}: routes {record["route_ids"]} / {record["paper"]["label"]}')
    points=[(c["x"],c["y"]) for c in record["crosses"]]
    cx,cy=record["centroid"]["x"],record["centroid"]["y"]
    colors=("#1f77b4","#ff7f0e","#2ca02c")
    for panel,half in enumerate((6.,max(.16,max(max(abs(x-cx),abs(y-cy)) for x,y in points)*1.5))):
        left=65+panel*590; top=95; size=490; scale=size/(2*half)
        def xy(x,y): return left+(x-cx+half)*scale,top+(cy+half-y)*scale
        parts.append(f'<defs><clipPath id="clip{panel}"><rect x="{left}" y="{top}" width="{size}" height="{size}"/></clipPath></defs>')
        parts.append(f'<text x="{left}" y="70" font-family="Arial" font-size="15">{"Bend context" if panel==0 else "Triangle detail"}: x/y scale equal; span {2*half:.6g} mm</text>')
        parts.append(f'<g clip-path="url(#clip{panel})" fill="none">')
        for n,rid in enumerate(record["route_ids"]):
            for seg in plot_by_id[rid]["segments"]:
                if seg["kind"]=="line":
                    x1,y1=xy(seg["x1"],seg["y1"]);x2,y2=xy(seg["x2"],seg["y2"])
                    command=f'M {x1} {y1} L {x2} {y2}'
                else:
                    from math import cos,sin,radians
                    a,b=radians(seg["start_deg"]),radians(seg["start_deg"]+seg["sweep_deg"])
                    x1,y1=xy(seg["cx"]+seg["r"]*cos(a),seg["cy"]+seg["r"]*sin(a))
                    x2,y2=xy(seg["cx"]+seg["r"]*cos(b),seg["cy"]+seg["r"]*sin(b))
                    large="1" if abs(seg["sweep_deg"])>180 else "0"
                    sweep="1" if seg["sweep_deg"]<0 else "0"
                    radius=seg["r"]*scale
                    command=f'M {x1} {y1} A {radius} {radius} 0 {large} {sweep} {x2} {y2}'
                parts.append(f'<path d="{command}" stroke="{colors[n]}" stroke-width="1.6"/>')
        coords=[xy(x,y) for x,y in points]
        parts.append('<polygon points="'+" ".join(f"{x},{y}" for x,y in coords)+'" stroke="#222" stroke-dasharray="3 3" stroke-width="1" fill="none"/>')
        for n,(x,y) in enumerate(coords):
            parts.append(f'<circle cx="{x}" cy="{y}" r="3" fill="#222"/>')
            if panel==1:
                parts.append(f'<text x="{x+6}" y="{y-6}" fill="#222" font-family="Arial" font-size="12">{("AB","AC","BC")[n]}</text>')
        parts.append('</g>')
        parts += [f'<rect x="{left}" y="{top}" width="{size}" height="{size}" stroke="#888" fill="none"/>',
                  f'<text x="{left}" y="605" font-family="Arial" font-size="12">X: {cx-half:.6f} .. {cx+half:.6f} mm; Y: {cy-half:.6f} .. {cy+half:.6f} mm</text>']
    for i,rid in enumerate(record["route_ids"]):
        parts.append(f'<text x="{70+i*370}" y="640" fill="{colors[i]}" font-family="Arial">route {rid}</text>')
    parts.append('</svg>')
    return "\n".join(parts)


def audit(root, source):
    out=root/"outputs"
    protected=[p for folder in ("src","tests","scripts","outputs","docs") for p in (root/folder).rglob("*")
               if p.is_file() and not p.name.startswith(PREFIX)]
    inputs=[source/"fiberBoard512.xlsx",source/"fiberBoard0data.xlsx"]
    before={str(p):digest(p) for p in protected+inputs}
    plot=json.loads((out/(BASE+"_plot_geometry.json")).read_text())
    saved_summary=json.loads((out/(BASE+"_multi_crossing_summary.json")).read_text())
    physical_summary=json.loads((out/(BASE+"_physical_summary.json")).read_text())
    loss=json.loads((out/(BASE+"_loss_summary.json")).read_text())
    ab=json.loads((out/"step_8_5_top_u_order_ab_summary.json").read_text())
    physical_path=out/(BASE+"_physical_events.jsonl")
    assert digest(physical_path)==saved_summary["physical_events_sha256"]==loss["physical_events_sha256"]
    assert ab["control_config"]["top_u_primary_order"]=="ascending"
    assert ab["physical_source_sha256"]==digest(physical_path)
    assert physical_summary["physical"]["pair_count"]==130816 and not physical_summary["errors"]
    assert [digest(p) for p in inputs]==physical_summary["source_sha256"]==loss["source_hashes"]
    assert saved_summary["jsonl_truncated"] is False
    ws=load_legacy_512_snapshot(*inputs)
    waveguides={w.id:w for w in ws}
    plot_by_id={r["id"]:r for r in plot["routes"]}
    assert len(plot["routes"])==len(plot_by_id)==len(ws)==512
    special={r["id"] for r in plot["routes"] if r["special"]}
    assert len(special)==58
    routes={rid:deserialize_plot(r) for rid,r in plot_by_id.items()}
    endpoints={rid:physical_endpoints(w) for rid,w in waveguides.items()}
    owners={rid:chain_ownership(r,endpoints[rid]) for rid,r in routes.items()}
    orders=geometric_pmt_order(ws)
    categories={}
    for rid,w in waveguides.items():
        prep=prepare_waveguide_2d(w,150,0)
        a,b=_algorithmic_endpoints(w,prep,1e-9)
        sa="top" if a.position.y==150 else "bottom"
        sb="top" if b.position.y==150 else "bottom"
        categories[rid]="special-Z" if rid in special else sa+"-U" if prep.route_type=="u" else sa+"->"+sb+" Z"
    # Verify saved primitive indices/coordinates against ALL saved raw events.
    raw=defaultdict(list)
    for e in read_lines(out/(BASE+"_exact_events.jsonl")):
        a,b=e["route_id_a"],e["route_id_b"]
        if e["point"] is not None:
            point=Point2D(**e["point"])
            for rid,idx in ((a,e["segment_index_a"]),(b,e["segment_index_b"])):
                assert point_on_primitive(point,routes[rid].segments[idx])
        raw[tuple(sorted((a,b)))].append(e)
    events=[]
    for e in read_lines(physical_path):
        e["point"]=Point2D(**e["point"]) if e["point"] else None
        events.append(PhysicalRouteIntersection(**e))
    pairs=build_crossing_pair_map(events)
    assert len(events)==55935 and len(pairs)==49502
    saved=read_lines(out/(BASE+"_multi_crossings.jsonl"))
    assert len(saved)==saved_summary["multi_waveguide_crossing_count"]==318
    assert len({tuple(s["route_ids"]) for s in saved})==318
    frozen=deepcopy((routes,ws,events,saved))
    records=[]; flat_crosses=[]
    for number,item in enumerate(saved,1):
        ids=tuple(item["route_ids"])
        checked=classify_multi_crossing(ids,pairs,.125,1e-9)
        assert checked.classification==item["classification"]=="multi_waveguide_crossing"
        assert list(checked.side_lengths_mm)==item["side_lengths_mm"]
        cross_records=[]
        for key,name in zip(combinations(ids,2),("point_ab","point_ac","point_bc")):
            assert len(pairs[key])==1
            point=pairs[key][0].point
            assert asdict(point)==item[name]
            matches=[e for e in raw[key] if e["point"] is not None and
                     hypot(e["point"]["x"]-point.x,e["point"]["y"]-point.y)<=1e-9]
            assert matches
            members={}
            for rid in key:
                indices=[e["segment_index_a"] if e["route_id_a"]==rid else e["segment_index_b"] for e in matches]
                members[rid]=primitive_attribution(routes[rid],point,indices,owners[rid])
            cross=dict(multi_id=f"M{number:04}",route_a=key[0],route_b=key[1],x=point.x,y=point.y,
                       primitive_a=members[key[0]],primitive_b=members[key[1]],
                       raw_membership_count=len(matches))
            cross["endpoint_bend_related"]=any(p["type"]=="ARC" and p["endpoint_owner"]
                 for k in ("primitive_a","primitive_b") for p in cross[k])
            cross["neighbor_relations"]=arc_vertical_relations(cross,orders)
            cross["segment_pair_type"]=pair_token(cross)
            cross_records.append(cross)
            row={k:cross[k] for k in ("multi_id","route_a","route_b","x","y")}
            for side in ("a","b"):
                members=cross["primitive_"+side]
                one=members[0] if len(members)==1 else None
                for field,source_field in (("type","type"),("index","segment_index"),
                                          ("orientation","orientation"),("endpoint_owner","endpoint_owner")):
                    row[f"primitive_{side}_{field}"]=one[source_field] if one else [p[source_field] for p in members]
                row[f"primitive_{side}_details"]=members
            row.update(segment_pair_type=cross["segment_pair_type"],
                       endpoint_bend_related=bool(cross["endpoint_bend_related"]),
                       neighbor_relations=cross["neighbor_relations"])
            flat_crosses.append(row)
        record=dict(multi_id=f"M{number:04}",route_ids=list(ids),
            route_categories={rid:categories[rid] for rid in ids},
            pmt_pairs={rid:[waveguides[rid].start_port.pmt_id,waveguides[rid].end_port.pmt_id] for rid in ids},
            endpoints={rid:endpoints[rid] for rid in ids},
            centroid=dict(x=sum(c["x"] for c in cross_records)/3,y=sum(c["y"] for c in cross_records)/3),
            bounding_box=dict(xmin=min(c["x"] for c in cross_records),xmax=max(c["x"] for c in cross_records),
                              ymin=min(c["y"] for c in cross_records),ymax=max(c["y"] for c in cross_records)),
            side_lengths_mm=item["side_lengths_mm"],crosses=cross_records,
            endpoint_bend_cross_count=sum(bool(c["endpoint_bend_related"]) for c in cross_records),
            topology_signature=topology_signature(cross_records),
            simple_signature=topology_signature(cross_records,False))
        record["per_route_crossings"]={rid:[
            dict(pair=[c["route_a"],c["route_b"]],point=dict(x=c["x"],y=c["y"]),
                 primitives=c["primitive_a"] if c["route_a"]==rid else c["primitive_b"])
            for c in cross_records if rid in (c["route_a"],c["route_b"])] for rid in ids}
        record["paper"]=classify_paper_like(cross_records)
        arc_uses=[(c[k],p) for c in cross_records for k,pk in (("route_a","primitive_a"),("route_b","primitive_b"))
                  for p in c[pk] if p["type"]=="ARC"]
        lr={p["endpoint_owner"]["physical_end"] for _,p in arc_uses if p["endpoint_owner"]}
        tb={p["endpoint_owner"]["side"] for _,p in arc_uses if p["endpoint_owner"]}
        record["physical_region"]=dict(left_right=next(iter(lr)) if len(lr)==1 else "MIXED" if lr else "NO_ENDPOINT_ARC",
                                       top_bottom=next(iter(tb)) if len(tb)==1 else "MIXED" if tb else "NO_ENDPOINT_ARC")
        relations=[rel for c in cross_records for rel in c["neighbor_relations"]]
        record["diagnostic_flags"]=[]
        if not arc_uses: record["diagnostic_flags"].append("NO_ARC")
        if any(c["segment_pair_type"]=="ARC x ARC" for c in cross_records): record["diagnostic_flags"].append("ARC_X_ARC")
        if any(rel["neighbor_relation"]=="NON_ADJACENT" for rel in relations): record["diagnostic_flags"].append("NON_ADJACENT_BEND_VERTICAL")
        if any(len({p["segment_index"] for rid,p in arc_uses if rid==route})>1 for route in ids):
            record["diagnostic_flags"].append("TWO_BENDS_SAME_ROUTE")
        if any(rid in special for rid in ids): record["diagnostic_flags"].append("SPECIAL_RELATED")
        if record["paper"]["reason"]=="NO_TWO_CROSS_VERTICAL_CARRIER":
            record["diagnostic_flags"].append("NO_PAPER_VERTICAL_CARRIER")
        record["spatial_group"]=("special_related" if any(rid in special for rid in ids) else
                "top_U_related" if any(categories[rid]=="top-U" for rid in ids) else
                "bottom_U_related" if any(categories[rid]=="bottom-U" for rid in ids) else "cross_side_Z")
        records.append(record)
    assert len(flat_crosses)==3*len(records)==954
    assert frozen==(routes,ws,events,saved)
    # Statistics: cross occurrences can repeat the same physical pair across triplets.
    pair_types=Counter(c["segment_pair_type"] for r in records for c in r["crosses"])
    topology=Counter(r["topology_signature"] for r in records)
    simple=Counter(r["simple_signature"] for r in records)
    paper=Counter(r["paper"]["label"] for r in records)
    flags=Counter(f for r in records for f in r["diagnostic_flags"])
    for name in ("NO_ARC","ARC_X_ARC","NON_ADJACENT_BEND_VERTICAL","TWO_BENDS_SAME_ROUTE",
                 "SPECIAL_RELATED","NO_PAPER_VERTICAL_CARRIER"):
        flags.setdefault(name,0)
    burden=Counter(rid for r in records for rid in r["route_ids"])
    pmt_burden=Counter(pid for r in records for pid in {p for ps in r["pmt_pairs"].values() for p in ps})
    pmt_connection_burden=Counter(tuple(sorted(pair)) for r in records for pair in {tuple(sorted(ps)) for ps in r["pmt_pairs"].values()})
    neighbor_burden=Counter()
    adj_multis=set(); evaluated_multis=set(); related_pmt_burden=Counter()
    route_roles=defaultdict(Counter)
    category_stats={}
    for category in ("top-U","bottom-U","top->bottom Z","bottom->top Z","special-Z"):
        occurrences=Counter(); sides=Counter(); multi_lr=defaultdict(set); multi_tb=defaultdict(set)
        for r in records:
            for c in r["crosses"]:
                for rk,pk in (("route_a","primitive_a"),("route_b","primitive_b")):
                    if categories[c[rk]]!=category: continue
                    for p in c[pk]:
                        if p["type"]=="ARC" and p["endpoint_owner"]:
                            owner=p["endpoint_owner"]
                            occurrences[owner["physical_end"]]+=1
                            sides[owner["side"]+":"+owner["physical_end"]]+=1
                            multi_lr[owner["physical_end"]].add(r["multi_id"])
                            multi_tb[owner["side"]].add(r["multi_id"])
        total=sum(occurrences.values())
        category_stats[category]=dict(arc_owner_occurrences=dict(occurrences),
            occurrence_proportions={k:v/total for k,v in occurrences.items()} if total else {},
            top_bottom_left_right=dict(sides),multi_left_right={k:len(v) for k,v in multi_lr.items()},
            multi_top_bottom={k:len(v) for k,v in multi_tb.items()},
            observed_side="INSUFFICIENT_EVIDENCE" if not total else "BIDIRECTIONAL" if
                occurrences["LEFT"] and occurrences["RIGHT"] else "OBSERVED_LEFT_ONLY" if
                occurrences["LEFT"] else "OBSERVED_RIGHT_ONLY" if occurrences["RIGHT"] else "AMBIGUOUS")
    for r in records:
        neighbor_pairs=set(); bend_pmts=set()
        for rid in r["route_ids"]:
            roles=set()
            for c in r["crosses"]:
                if rid not in (c["route_a"],c["route_b"]): continue
                ps=c["primitive_a"] if c["route_a"]==rid else c["primitive_b"]
                for p in ps:
                    if p["type"]=="LINE": roles.add(p["orientation"])
                    elif p["endpoint_owner"]: roles.add(p["endpoint_owner"]["physical_end"]+"_BEND")
            route_roles[rid].update(roles)
        for c in r["crosses"]:
            for pk in ("primitive_a","primitive_b"):
                bend_pmts.update(p["endpoint_owner"]["pmt_id"] for p in c[pk] if p["type"]=="ARC" and p["endpoint_owner"])
            for rel in c["neighbor_relations"]:
                evaluated_multis.add(r["multi_id"])
                if rel["neighbor_relation"] in ("LEFT_GEOMETRIC_NEIGHBOR","RIGHT_GEOMETRIC_NEIGHBOR"):
                    adj_multis.add(r["multi_id"])
                    neighbor_pairs.add(tuple(sorted((rel["arc_owner"]["pmt_id"],rel["vertical_owner"]["pmt_id"]))))
        neighbor_burden.update(neighbor_pairs);related_pmt_burden.update(bend_pmts)
    top_routes=[dict(route_id=rid,category=categories[rid],pmt_pair=[
        waveguides[rid].start_port.pmt_id,waveguides[rid].end_port.pmt_id],
        multi_count=n,involvement=dict(route_roles[rid])) for rid,n in sorted(burden.items(),key=lambda t:(-t[1],t[0]))[:20]]
    def ranking(counter):
        return [dict(id=k,count=v) for k,v in sorted(counter.items(),key=lambda t:(-t[1],t[0]))[:20]]
    cases=[]
    selectors=[
        ("most_common_topology",lambda r:r["topology_signature"]==topology.most_common(1)[0][0]),
        ("endpoint_bend",lambda r:r["endpoint_bend_cross_count"]>0),
        ("non_paper_like",lambda r:r["paper"]["label"]=="NON_PAPER_LIKE"),
        ("special_related",lambda r:"SPECIAL_RELATED" in r["diagnostic_flags"])]
    selected=set()
    for label,predicate in selectors:
        match=next((r for r in records if predicate(r) and r["multi_id"] not in selected),None)
        if match is None: match=next((r for r in records if predicate(r)),None)
        if match:
            selected.add(match["multi_id"])
            filename=f"{PREFIX}_case_{label}.svg"
            (out/filename).write_text(case_svg(match,plot_by_id),encoding="utf-8")
            cases.append(dict(purpose=label,svg=filename,record=match))
    write_csv(out/(PREFIX+"_multi_triplets.csv"),[
        {k:v for k,v in r.items() if k!="crosses"} for r in records])
    write_csv(out/(PREFIX+"_multi_crosses.csv"),flat_crosses)
    (out/(PREFIX+"_multi_centroids.svg")).write_text(scatter_svg(records),encoding="utf-8")
    unchanged=all(digest(Path(p))==h for p,h in before.items())
    assert unchanged
    summary=dict(verdict="PASS",baseline=dict(order="ascending",exclusive="A",guard="OFF",
        width_mm=.05,spacing_mm=.125,pitch_mm=.175,radius_mm=5,analytic_routes=512,ordinary=454,special=58,
        saved_pair_coverage=130816),
        multi_count=len(records),cross_attribution_rows=len(flat_crosses),
        unique_attributed_physical_pairs=len({(c["route_a"],c["route_b"]) for r in records for c in r["crosses"]}),
        segment_pair_counts=dict(pair_types),endpoint_bend_cross_histogram={str(n):sum(r["endpoint_bend_cross_count"]==n for r in records) for n in range(4)},
        endpoint_bend_multi_count=sum(r["endpoint_bend_cross_count"]>0 for r in records),
        endpoint_bend_multi_fraction=sum(r["endpoint_bend_cross_count"]>0 for r in records)/len(records),
        category_stats=category_stats,
        global_arc_owner_occurrences=dict(sum((Counter(v["arc_owner_occurrences"]) for v in category_stats.values()),Counter())),
        global_multi_physical_regions=dict(Counter(r["physical_region"]["left_right"] for r in records)),
        global_multi_vertical_regions=dict(Counter(r["physical_region"]["top_bottom"] for r in records)),
        spatial_grid_25mm=[dict(xmin=x,ymin=y,count=sum(x<=r["centroid"]["x"]<x+25 and y<=r["centroid"]["y"]<y+25 for r in records))
                           for y in range(0,150,25) for x in range(0,150,25)],
        neighbor_relation_occurrences=dict(Counter(rel["neighbor_relation"] for r in records for c in r["crosses"] for rel in c["neighbor_relations"])),
        adjacent_pmt_multi_count=len(adj_multis),adjacent_pmt_fraction_all_multi=len(adj_multis)/len(records),
        arc_vertical_evaluable_multi_count=len(evaluated_multis),
        adjacent_fraction_evaluable=len(adj_multis)/len(evaluated_multis) if evaluated_multis else None,
        paper_labels=dict(paper),diagnostic_flags=dict(flags),
        top20_topologies=ranking(topology),simple_topologies=ranking(simple),top20_routes=top_routes,
        per_route=[dict(route_id=rid,category=categories[rid],
                       pmt_pair=[waveguides[rid].start_port.pmt_id,waveguides[rid].end_port.pmt_id],
                       multi_count=burden[rid],involvement={role:route_roles[rid][role] for role in
                       ("LEFT_BEND","RIGHT_BEND","HORIZONTAL","VERTICAL","OTHER")})
                   for rid in sorted(waveguides)],
        top20_pmts_all_participant_endpoints=ranking(pmt_burden),
        top20_pmts_endpoint_bend=ranking(related_pmt_burden),
        top20_connection_pmt_pairs=ranking(pmt_connection_burden),
        top20_geometric_neighbor_pairs=ranking(neighbor_burden),
        spatial_groups=dict(Counter(r["spatial_group"] for r in records)),
        centroids=[dict(multi_id=r["multi_id"],**r["centroid"],group=r["spatial_group"]) for r in records],
        case_studies=cases,boundary_count_separate=saved_summary["boundary_triangle_count"],
        outside_single_cross_count_separate=saved_summary["outside_legacy_assumption_triangles"],
        consistency=dict(saved_multi_count_match=True,three_single_crosses_per_multi=True,
            saved_physical_coordinates_exact_match=True,raw_geometry_membership_checked=True,
            input_objects_unchanged=True,protected_files_unchanged=unchanged),
        input_sha256={str(p):h for p,h in before.items() if p.endswith((".json",".jsonl",".xlsx"))},
        paper_rule="A-E plus unique repeated endpoint bend in HV/AV/AH motif; other A-E motifs ambiguous",
        ownership_rule="Unique chain from each real endpoint through initial lines to first arc; no distance threshold")
    (out/(PREFIX+"_multi_attribution_summary.json")).write_text(json.dumps(summary,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in summary.items() if k not in ("case_studies","centroids","input_sha256")},indent=2))
    return summary


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("legacy_directory",type=Path)
    args=parser.parse_args()
    audit(Path(__file__).resolve().parents[1],args.legacy_directory)
