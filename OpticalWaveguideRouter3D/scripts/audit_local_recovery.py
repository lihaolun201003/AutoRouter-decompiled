"""Read saved ascending baseline; four fixed-case exhaustive sandbox scans."""
import sys, json, csv, importlib.util, traceback
from pathlib import Path
from hashlib import sha256
from collections import Counter
from dataclasses import asdict
from itertools import combinations
from time import perf_counter
ROOT=Path(sys.argv[1]).resolve()
OUT=Path(sys.argv[2]); OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT))
from local_recovery_feasibility import *
from src.io import load_legacy_512_snapshot
from src.router_2d import prepare_waveguide_2d,build_track_grid_2d,TrackPolicyConfig
from src.multi_attribution import deserialize_plot
from src.models import Point2D,LineSegment2D
from src.physical_intersections import PhysicalRouteIntersection
from src.multi_crossing import build_crossing_pair_map

def digest(p): return sha256(p.read_bytes()).hexdigest()
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def lines(p): return [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s]
def save(name,data): (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

protected={str(p):digest(p) for folder in ('src','tests','scripts','outputs','docs','config','data')
           for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)
           and not p.name.startswith('step_8_5_m1_6_')}
save('step_8_5_m1_6_protected_hashes.json',protected)
out=ROOT/'outputs'
summary=read(out/'step_8_5_m1_5_multi_attribution_summary.json')
with (out/'step_8_5_m1_5_multi_triplets.csv').open(encoding='utf-8-sig',newline='') as f:
    records=list(csv.DictReader(f))
for r in records:
    for k in ('route_ids','paper','diagnostic_flags','route_categories'):r[k]=json.loads(r[k])
with (out/'step_8_5_m1_5_multi_crosses.csv').open(encoding='utf-8-sig',newline='') as f:
    crosses=list(csv.DictReader(f))
multis={tuple(r['route_ids']) for r in records}
assert len(records)==len(multis)==summary['multi_count']==318 and len(crosses)==954
assert Counter(c['multi_id'] for c in crosses)==Counter({r['multi_id']:3 for r in records})
scores=victim_scores(multis)
assert all(scores[r['route_id']]==r['multi_count'] for r in summary['per_route'])
plot=read(out/'step_8_5_legacy_512_plot_geometry.json')
routes={r['id']:deserialize_plot(r) for r in plot['routes']}
special={r['id'] for r in plot['routes'] if r['special']}
assert len(routes)==512 and len(special)==58
legacy=ROOT.parent/'自动排布'/'AutoRouter'
inputs=[legacy/'fiberBoard512.xlsx',legacy/'fiberBoard0data.xlsx']
input_hashes={str(p):digest(p) for p in inputs}
ws=load_legacy_512_snapshot(*inputs)
waveguides={w.id:w for w in ws}
preps={w.id:prepare_waveguide_2d(w,150.,0.) for w in ws}
grid=build_track_grid_2d(TrackPolicyConfig(150.,.05,.125,5.))
occupancy=[None]*len(grid)
for rid,r in routes.items():
    if rid in special:continue
    horizontal=[s for s in r.segments if isinstance(s,LineSegment2D) and abs(s.start.y-s.end.y)<1e-9]
    assert len(horizontal)==1
    i=min(range(len(grid)),key=lambda i:abs(grid[i]-horizontal[0].start.y))
    assert abs(grid[i]-horizontal[0].start.y)<1e-9 and occupancy[i] is None
    occupancy[i]=rid
    rebuilt=candidate_geometry(waveguides[rid],preps[rid],i,grid,special)
    assert len(rebuilt.segments)==len(r.segments)
    for a,b in zip(rebuilt.segments,r.segments):
        assert type(a)==type(b) and distance(a.start,b.start)<1e-9 and distance(a.end,b.end)<1e-9
        if isinstance(a,ArcSegment2D):assert distance(a.center,b.center)<1e-9 and abs(a.sweep_rad-b.sweep_rad)<1e-9
assert len(grid)==800 and sum(x is not None for x in occupancy)==454
events=[]
for e in lines(out/'step_8_5_legacy_512_physical_events.jsonl'):
    e['point']=Point2D(**e['point']) if e['point'] else None
    events.append(PhysicalRouteIntersection(**e))
pairs=build_crossing_pair_map(events)
assert len(events)==55935 and all(e.kind=='cross' for e in events)
old_summary=read(out/'step_8_5_legacy_512_multi_crossing_summary.json')
assert old_summary['physical_events_sha256']==digest(out/'step_8_5_legacy_512_physical_events.jsonl')
for t in multis:assert classify_multi_crossing(t,pairs).classification=='multi_waveguide_crossing'
alternate={r:len(grid)-454 for r in routes if r not in special}
table=[]
for r in records:
    ids=r['route_ids']; values=sorted(scores[i] for i in ids)
    lowest=[i for i in ids if scores[i]==values[0]]
    table.append(dict(multi_id=r['multi_id'],route_ids=ids,counts={i:scores[i] for i in ids},
        min=values[0],middle=values[1],max=values[2],lowest=lowest,
        lowest_ordinary=[i for i in lowest if i not in special],lowest_special=[i for i in lowest if i in special],
        ordinary_order=victim_order(ids,scores,special,alternate)))
stats=dict(unique_lowest=sum(len(r['lowest'])==1 for r in table),tied_lowest=sum(len(r['lowest'])>1 for r in table),
    lowest_only_ordinary=sum(bool(r['lowest_ordinary']) and not r['lowest_special'] for r in table),
    lowest_only_special=sum(bool(r['lowest_special']) and not r['lowest_ordinary'] for r in table),
    lowest_mixed=sum(bool(r['lowest_special']) and bool(r['lowest_ordinary']) for r in table),
    no_movable=sum(not r['ordinary_order'] for r in table),
    distributions={k:dict(sorted(Counter(r[k] for r in table).items())) for k in ('min','middle','max')},
    means={k:sum(r[k] for r in table)/318 for k in ('min','middle','max')},
    skip_special_first_ordinary_scores=dict(Counter(scores[r['ordinary_order'][0]] for r in table if r['lowest_special'] and not r['lowest_ordinary'])))
save('step_8_5_m1_6_victim_statistics.json',dict(statistics=stats,triplets=table))
print(json.dumps(stats),flush=True)
selectors=[('A_paper_ordinary',lambda r:r['paper']['label']=='PAPER_LIKE_LOCAL_MULTI' and 'SPECIAL_RELATED' not in r['diagnostic_flags']),
 ('B_cross_side_nonpaper',lambda r:r['paper']['label']=='NON_PAPER_LIKE' and 'NON_ADJACENT_BEND_VERTICAL' in r['diagnostic_flags']),
 ('C_arc_arc',lambda r:'ARC_X_ARC' in r['diagnostic_flags']),
 ('D_special_carrier',lambda r:'SPECIAL_RELATED' in r['diagnostic_flags'] and r['paper']['label']=='PAPER_LIKE_LOCAL_MULTI')]
results=[]
frozen=deepcopy((occupancy,waveguides,preps,routes,pairs,multis,scores))
for label,predicate in selectors:
    record=next(r for r in records if predicate(r))
    target=tuple(record['route_ids']); victim=victim_order(target,scores,special,alternate)[0]
    free=released_occupancy(occupancy,victim)
    scan=range(800) if preps[victim].side=='bottom' else range(799,-1,-1)
    candidates=[i for i in scan if free[i] is None]
    rows=[];start=perf_counter();best=None
    for n,i in enumerate(candidates):
        try:
            score,curve,delta=evaluate(target,victim,i,grid,occupancy,waveguides,preps,routes,pairs,multis,special)
            score['geometry_valid']=True
            if score['accepted'] and (best is None or candidate_rank(score)<candidate_rank(best[0])):best=(score,curve)
        except ValueError as ex:
            score=dict(track_index=i,geometry_valid=False,error=str(ex),accepted=False)
        rows.append(score)
        if n%50==0:print(label,record['multi_id'],'victim',victim,n+1,'/',len(candidates),round(perf_counter()-start,2),flush=True)
    valid=[r for r in rows if r['geometry_valid']]
    result=dict(label=label,multi_id=record['multi_id'],target=target,victim=victim,
        victim_order=victim_order(target,scores,special,alternate),scores={r:scores[r] for r in target},
        candidate_count=len(rows),geometry_valid=len(valid),anomaly_free=sum(not r['noncross_anomalies'] for r in valid),
        minimum_M_after=min((r['M_after'] for r in valid),default=None),
        strict_improvement_candidates=sum(r['accepted'] for r in rows),best=best[0] if best else None,
        seconds=perf_counter()-start)
    save('step_8_5_m1_6_'+label+'_candidates.json',rows)
    results.append(result)
    assert frozen==(occupancy,waveguides,preps,routes,pairs,multis,scores)
    save('step_8_5_m1_6_probe_summary.json',dict(status='FEASIBILITY_ONLY_NO_COMMIT',statistics=stats,cases=results))
    print(json.dumps(result),flush=True)
assert all(digest(Path(p))==h for p,h in protected.items())
assert all(digest(Path(p))==h for p,h in input_hashes.items())
save('step_8_5_m1_6_integrity.json',dict(protected_count=len(protected),unchanged=True,input_hashes=input_hashes,object_equality=True))
