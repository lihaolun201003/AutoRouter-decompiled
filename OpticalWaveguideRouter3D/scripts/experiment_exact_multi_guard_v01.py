"""Step L V0.2 experiment; G0 gate precedes opt-in guard, no baseline adoption."""
from pathlib import Path
from collections import Counter
from dataclasses import asdict
from itertools import combinations
from time import perf_counter
from math import degrees
import json
from src.io import load_legacy_512_snapshot
from src.router_2d import (TrackPolicyConfig, prepare_waveguides_2d, assign_tracks_2d,
    generate_assigned_routes_2d, _algorithmic_endpoints)
from src.geometry import smooth_orthogonal_route_2d, build_special_z_smoothed_route_2d
from src.collision import find_smoothed_route_intersections_2d, find_smoothed_route_self_intersections_2d
from src.physical_intersections import consolidate_route_intersections_2d
from src.multi_crossing import build_crossing_pair_map, build_crossing_graph, enumerate_crossing_triangles, classify_multi_crossing
from src.multi_crossing_guard import ExactMultiCrossingGuard
from src.loss_analysis import analyze_route_loss_mm, statistics, crossing_angle_statistics
from scripts.experiment_top_u_order_v01 import metrics, make_svg, digest, read_lines
from scripts.validate_legacy_512_exact import check_route

PREFIX = 'step_8_5_exact_multi_guard'


def analyze(routes, ws, top, bottom, special, out, label):
    """Independent full post-validation, never consume candidate pair cache."""
    timing = {}; objects = []; raw_counts = Counter(); self_counts = Counter()
    t = perf_counter()
    for route in routes:
        assert not check_route(route, ws[route.waveguide_id])
        self_counts.update(e.kind for e in find_smoothed_route_self_intersections_2d(route))
    assert not sum(self_counts.values())
    timing['self_validation'] = perf_counter()-t
    collision = consolidation = 0.; count = 0
    name = PREFIX + ('_g0' if label == 'G0' else '')
    with (out/(name+'_physical_events.jsonl')).open('w',encoding='utf-8') as sink:
        for a,b in combinations(routes,2):
            t=perf_counter(); raw=find_smoothed_route_intersections_2d(a,b); collision+=perf_counter()-t
            raw_counts.update(e.kind for e in raw)
            t=perf_counter(); events=consolidate_route_intersections_2d(a,b,raw); consolidation+=perf_counter()-t
            objects.extend(events)
            for e in events: sink.write(json.dumps(asdict(e))+'\n')
            count+=1
            if count%30000==0: print(label,'post pairs',count,flush=True)
    timing['final_full_collision']=collision
    timing['post_physical_consolidation']=consolidation
    physical=[asdict(e) for e in objects]
    metric,split=metrics(physical,top,bottom,special)
    with (out/(name+'_double_pairs.jsonl')).open('w',encoding='utf-8') as sink:
        for pair,events in split['double'].items(): sink.write(json.dumps(dict(route_ids=pair,crossings=events))+'\n')
    t=perf_counter(); pairs=build_crossing_pair_map(objects); graph=build_crossing_graph(pairs)
    counts=Counter(); composition=Counter(); detected=set()
    with (out/(name+'_multi_crossings.jsonl')).open('w',encoding='utf-8') as sink:
        for ids in enumerate_crossing_triangles(graph):
            result=classify_multi_crossing(ids,pairs,.125,1e-9)
            counts[result.classification]+=1
            if result.classification=='multi_waveguide_crossing':
                detected.add(ids)
                n=sum(i in special for i in ids)
                composition[n]+=1
                sink.write(json.dumps(asdict(result))+'\n')
    timing['post_multi_analysis']=perf_counter()-t
    losses=[analyze_route_loss_mm(r) for r in routes]
    loss_stats={k:statistics([r[k] for r in losses]) for k in
        ('total_length_mm','propagation_loss_db','bend_loss_db','known_non_crossing_loss_db')}
    angles=crossing_angle_statistics(physical,[r.waveguide_id for r in routes])['degrees']
    angles['below_20_count']=sum(e.kind=='cross' and degrees(e.crossing_angle_rad)<20 for e in objects)
    return dict(route_count=len(routes),checked_pairs=count,physical=metric,angles=angles,losses=loss_stats,
        multi=dict(counts),multi_composition={key:composition[n] for n,key in enumerate((
        'ordinary/ordinary/ordinary','ordinary/ordinary/special','ordinary/special/special','special/special/special'))},
        ordinary_only_multi=composition[0],self_counts=dict(self_counts),raw_counts=dict(raw_counts),timings=timing),detected


def main():
    root=Path(__file__).resolve().parents[1];out=root/'outputs';started=perf_counter()
    sources=next(root.parent.glob('*/AutoRouter/fiberBoard0data.xlsx')).parent
    source=[sources/'fiberBoard512.xlsx',sources/'fiberBoard0data.xlsx']
    protected=[p for p in out.iterdir() if p.is_file() and not p.name.startswith(PREFIX)]+source
    hashes={str(p):digest(p) for p in protected}
    ws=load_legacy_512_snapshot(*source);ww={w.id:w for w in ws}
    preps=prepare_waveguides_2d(ws,150,0);pp={p.waveguide_id:p for p in preps}
    cfg=TrackPolicyConfig(150,.05,.125,5,top_u_primary_order='descending')
    top={p.waveguide_id for p in preps if p.side=='top'}
    bottom={p.waveguide_id for p in preps if p.side=='bottom'}
    t=perf_counter();g0a=assign_tracks_2d(ws,preps,cfg)
    base_seconds=perf_counter()-t
    assert Counter(a.status for a in g0a)=={'assigned':454,'unsupported_geometry':58}
    special={a.waveguide_id for a in g0a if a.status=='unsupported_geometry'}
    special_curves=[build_special_z_smoothed_route_2d(i,ww[i].start_port.position,ww[i].end_port.position,5) for i in sorted(special)]
    def curves(assignments):
        skeletons=generate_assigned_routes_2d(ws,preps,assignments,top_y=150,bottom_y=0)
        return [smooth_orthogonal_route_2d(r,5) for r in skeletons]+special_curves
    print('G0 START',flush=True)
    g0,g0multi=analyze(curves(g0a),ww,top,bottom,special,out,'G0')
    # Mandatory stop-before-G1 gate, including all supplied regression metrics.
    m=g0['physical'];a=g0['angles'];loss=g0['losses']['known_non_crossing_loss_db']
    gate=(m['detailed_double']['topU-topU']==0 and m['double_pairs']==4530 and
        m['cross_points']==52129 and m['cross_pairs']==47599 and
        g0['multi']['multi_waveguide_crossing']==345 and
        g0['multi']['outside_legacy_single_cross_assumption']==613149 and
        a['below_20_count']==984 and abs(a['mean']-79.821642)<1e-6 and
        abs(loss['mean']-5.264615825627)<1e-9 and abs(loss['max']-6.187414816340)<1e-9)
    (out/(PREFIX+'_g0_gate.json')).write_text(json.dumps(dict(passed=gate,G0=g0),indent=2),encoding='utf-8')
    if not gate: raise RuntimeError('G0 regression failed; G1 NOT run.')
    print('G0 GATE PASSED',json.dumps(dict(ordinary_multi=g0['ordinary_only_multi'],angle=a,loss=loss)),flush=True)
    guard=ExactMultiCrossingGuard()
    t=perf_counter();g1a=assign_tracks_2d(ws,preps,cfg,guard=guard);guard_seconds=perf_counter()-t
    status=Counter(a.status for a in g1a)
    print('G1 ALLOCATED',dict(status),guard.summary(),flush=True)
    with (out/(PREFIX+'_rejections.jsonl')).open('w',encoding='utf-8') as sink:
        for record in guard.rejections:sink.write(json.dumps(record)+'\n')
    assigned={a.waveguide_id for a in g1a if a.status=='assigned'}
    assert len({a.track_index for a in g1a if a.status=='assigned'})==len(assigned)
    rebuilt=curves(g1a)
    assert all(r==guard.routes[r.waveguide_id] for r in rebuilt if r.waveguide_id not in special)
    g1,g1multi=analyze(rebuilt,ww,top,bottom,special,out,'G1')
    assert g1['ordinary_only_multi']==0,'Guard coverage/cache bug: ordinary multi survived'
    available=assigned|special
    added={tuple(r['route_ids']) for r in read_lines(out/'step_8_5_top_u_multi_crossing_added.jsonl')}
    j_status={ids:('not_comparable_due_to_unassigned' if not set(ids)<=available else
        'still_present' if ids in g1multi else 'eliminated') for ids in added}
    j_counts=Counter(j_status.values())
    aa={a.waveguide_id:a for a in g0a};bb={a.waveguide_id:a for a in g1a}
    displacement=[]
    for i in sorted(assigned):
        w=ww[i];start,_=_algorithmic_endpoints(w,pp[i],1e-9)
        group='topU' if i in top else 'bottomU' if i in bottom else 'top_to_bottomZ' if start.position.y==150 else 'bottom_to_topZ'
        delta=bb[i].track_index-aa[i].track_index
        displacement.append(dict(waveguide_id=i,group=group,delta=delta,abs_delta=abs(delta),
            guard_rejected_candidates=sum(r['waveguide_id']==i for r in guard.rejections)))
    def disp(rows):
        return dict(unchanged=sum(r['delta']==0 for r in rows),moved=sum(r['delta']!=0 for r in rows),
            abs_delta=statistics([r['abs_delta'] for r in rows]),
            rejected_candidate_tracks=sum(r['guard_rejected_candidates'] for r in rows))
    svg=out/(PREFIX+('_variant.svg' if len(assigned)==454 else '_partial.svg'))
    make_svg(rebuilt,special,svg)
    text=svg.read_text();text=text.replace('Experimental top-U primary reversal (not baseline)',
        'Exact multi-crossing guard ON (experimental, not baseline)')
    svg.write_text(text,encoding='utf-8')
    assert all(digest(Path(p))==h for p,h in hashes.items())
    summary=dict(version='Step 8.5-L V0.2',g0_gate_passed=True,config=asdict(cfg),
        G0=g0,G1=g1,G1_status=dict(status),guard=guard.summary(),
        step_j_added={k:j_counts[k] for k in ('eliminated','still_present','not_comparable_due_to_unassigned')},
        step_j_triplets=[dict(route_ids=k,status=v) for k,v in sorted(j_status.items())],
        new_multi_relative_to_G0=[list(t) for t in sorted(g1multi-g0multi)],
        removed_multi_relative_to_G0=[list(t) for t in sorted(g0multi-g1multi)],
        displacement=dict(overall=disp(displacement),by_group={g:disp([r for r in displacement if r['group']==g])
            for g in ('topU','bottomU','top_to_bottomZ','bottom_to_topZ')},per_route=displacement),
        assignments_G0=[asdict(a) for a in g0a],assignments_G1=[asdict(a) for a in g1a],
        runtime=dict(base_allocator=base_seconds,guard_allocator=guard_seconds,total=perf_counter()-started),
        ordinary_only_zero_invariant=True,prior_outputs_and_source_hashes_unchanged=True,
        protected_hashes=hashes,svg=str(svg))
    (out/(PREFIX+'_ab_summary.json')).write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print('COMPLETE',json.dumps(dict(status=dict(status),guard=guard.summary(),G1=g1,
        step_j=summary['step_j_added'],new_multi=len(g1multi-g0multi),displacement=disp(displacement),runtime=summary['runtime'])),flush=True)

if __name__=='__main__':main()