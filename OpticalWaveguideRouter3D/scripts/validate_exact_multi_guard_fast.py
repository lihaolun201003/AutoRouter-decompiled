"""Independent validation from frozen geometry; no candidate cache/verdict input."""
from collections import Counter
from dataclasses import asdict
from itertools import combinations
from math import degrees
from pathlib import Path
from time import perf_counter
import json
from src.models import Point2D,LineSegment2D,ArcSegment2D,SmoothedRoute2D
from src.physical_intersections import find_physical_route_intersections_2d
from src.collision import find_smoothed_route_self_intersections_2d
from src.multi_crossing import build_crossing_pair_map,build_crossing_graph,enumerate_crossing_triangles,classify_multi_crossing


def independent_validation(routes):
    """Rebuild every pair from geometry, ignoring any historical guard metadata."""
    started=perf_counter();events=[];pair_count=0;self_counts=Counter()
    for r in routes:self_counts.update(e.kind for e in find_smoothed_route_self_intersections_2d(r))
    for a,b in combinations(routes,2):
        events.extend(find_physical_route_intersections_2d(a,b));pair_count+=1
    pair_seconds=perf_counter()-started;t=perf_counter()
    pairs=build_crossing_pair_map(events);counts=Counter();multis=[]
    for ids in enumerate_crossing_triangles(build_crossing_graph(pairs)):
        result=classify_multi_crossing(ids,pairs,.125,1e-9);counts[result.classification]+=1
        if result.classification=='multi_waveguide_crossing':multis.append(result)
    return dict(events=events,multis=multis,counts=counts,checked_pairs=pair_count,self_counts=self_counts,
        pair_seconds=pair_seconds,multi_seconds=perf_counter()-t)


def deserialize(records):
    routes=[]
    for record in records:
        segments=[]
        for value in record['segments']:
            d=dict(value);kind=d.pop('type')
            for key in ('start','end','center'):
                if key in d:d[key]=Point2D(**d[key])
            segments.append((LineSegment2D if kind=='LineSegment2D' else ArcSegment2D)(**d))
        routes.append(SmoothedRoute2D(record['waveguide_id'],segments))
    return routes


def main():
    from src.io import load_legacy_512_snapshot
    from src.router_2d import prepare_waveguides_2d,_algorithmic_endpoints
    from src.geometry import build_special_z_smoothed_route_2d
    from src.loss_analysis import analyze_route_loss_mm,statistics,crossing_angle_statistics
    from scripts.experiment_top_u_order_v01 import metrics,make_svg,read_lines,digest
    root=Path(__file__).resolve().parents[1];out=root/'outputs';prefix='step_8_5_exact_multi_guard_fast'
    routing=json.loads((out/(prefix+'_routing.json')).read_text())
    assert routing['completed'] and routing['committed_ordinary']==454,'Full ordinary routing required'
    frozen_path=out/(prefix+'_geometry.json');frozen_hash=digest(frozen_path)
    ordinary=deserialize(json.loads(frozen_path.read_text()))
    source=next(root.parent.glob('*/AutoRouter/fiberBoard0data.xlsx')).parent
    ws=load_legacy_512_snapshot(source/'fiberBoard512.xlsx',source/'fiberBoard0data.xlsx')
    preps=prepare_waveguides_2d(ws,150,0);pp={p.waveguide_id:p for p in preps};ww={w.id:w for w in ws}
    top={p.waveguide_id for p in preps if p.side=='top'};bottom={p.waveguide_id for p in preps if p.side=='bottom'}
    special={a['waveguide_id'] for a in routing['off_assignments'] if a['status']=='unsupported_geometry'}
    assert len(special)==58
    def validate_and_save(routes,label):
        print('VALIDATE',label,len(routes),'routes',flush=True)
        result=independent_validation(routes)
        physical=[asdict(e) for e in result['events']]
        m,split=metrics(physical,top,bottom,special)
        angles=crossing_angle_statistics(physical,[r.waveguide_id for r in routes])['degrees']
        angles['below_20_count']=sum(e.kind=='cross' and degrees(e.crossing_angle_rad)<20 for e in result['events'])
        losses=[analyze_route_loss_mm(r) for r in routes]
        stats={k:statistics([r[k] for r in losses]) for k in ('total_length_mm','propagation_loss_db','bend_loss_db','known_non_crossing_loss_db')}
        composition=Counter(sum(i in special for i in r.route_ids) for r in result['multis'])
        for suffix,records in (('physical_events',physical),('multi_crossings',[asdict(r) for r in result['multis']]),
            ('double_pairs',[dict(route_ids=p,crossings=e) for p,e in split['double'].items()])):
            with (out/(prefix+'_'+label+'_'+suffix+'.jsonl')).open('w',encoding='utf-8') as f:
                for r in records:f.write(json.dumps(r)+'\n')
        summary=dict(route_count=len(routes),checked_pairs=result['checked_pairs'],physical=m,angles=angles,losses=stats,
            multi=dict(result['counts']),ordinary_only_multi=composition[0],
            multi_composition={name:composition[n] for n,name in enumerate(('ordinary/ordinary/ordinary',
                'ordinary/ordinary/special','ordinary/special/special','special/special/special'))},
            self_counts=dict(result['self_counts']),pair_seconds=result['pair_seconds'],multi_seconds=result['multi_seconds'])
        (out/(prefix+'_'+label+'_validation.json')).write_text(json.dumps(summary,indent=2))
        print(label,'RESULT',json.dumps(summary),flush=True)
        return summary,{r.route_ids for r in result['multis']}
    o,_=validate_and_save(ordinary,'ordinary')
    assert o['checked_pairs']==102831 and o['ordinary_only_multi']==0 and not sum(o['self_counts'].values()),'Independent invariant failed'
    full=ordinary+[build_special_z_smoothed_route_2d(i,ww[i].start_port.position,ww[i].end_port.position,5) for i in sorted(special)]
    g,multis=validate_and_save(full,'global');assert g['checked_pairs']==130816
    g0=json.loads((out/'step_8_5_exact_multi_guard_g0_gate.json').read_text())['G0']
    g0multis={tuple(r['route_ids']) for r in read_lines(out/'step_8_5_exact_multi_guard_g0_multi_crossings.jsonl')}
    added={tuple(r['route_ids']) for r in read_lines(out/'step_8_5_top_u_multi_crossing_added.jsonl')}
    off={r['waveguide_id']:r for r in routing['off_assignments']};displacements=[]
    for r in routing['assignments']:
        i=r['waveguide_id']
        if r['status']!='assigned':continue
        start,_=_algorithmic_endpoints(ww[i],pp[i],1e-9)
        group='topU' if i in top else 'bottomU' if i in bottom else 'top_to_bottomZ' if start.position.y==150 else 'bottom_to_topZ'
        displacements.append(dict(waveguide_id=i,group=group,delta=r['track_index']-off[i]['track_index']))
    def displacement(rows):return dict(moved=sum(r['delta']!=0 for r in rows),abs_delta=statistics([abs(r['delta']) for r in rows]))
    svg=out/(prefix+'_variant.svg');make_svg(full,special,svg)
    svg.write_text(svg.read_text().replace('Experimental top-U primary reversal (not baseline)','Fast exact multi guard (experimental, not baseline)'))
    assert digest(frozen_path)==frozen_hash
    summary=dict(G0=g0,ordinary_validation=o,G1=g,routing=routing,
        step_j_added=dict(eliminated=len(added-multis),still_present=len(added&multis),not_comparable_due_to_unassigned=0),
        new_multi_relative_to_G0=[list(t) for t in sorted(multis-g0multis)],
        displacement=dict(overall=displacement(displacements),per_route=displacements,
            by_group={name:displacement([r for r in displacements if r['group']==name]) for name in ('topU','bottomU','top_to_bottomZ','bottom_to_topZ')}),
        frozen_geometry_hash=frozen_hash,independent_validation=True,svg=str(svg))
    (out/(prefix+'_ab_summary.json')).write_text(json.dumps(summary,indent=2))
    print('FINAL COMPLETE',flush=True)

if __name__=='__main__':main()