"""Independent winner verification from saved geometry; never reads delta caches."""
import sys,json,csv
from pathlib import Path
from itertools import combinations
from collections import Counter
from time import perf_counter
root=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]);sys.path.insert(0,str(root))
from src.multi_attribution import deserialize_plot
from src.router_2d import prepare_waveguide_2d,generate_assigned_routes_2d,TrackAssignment,TrackPolicyConfig,build_track_grid_2d
from src.geometry import smooth_orthogonal_route_2d
from src.collision import find_smoothed_route_self_intersections_2d
from src.physical_intersections import find_physical_route_intersections_2d
from src.multi_crossing import classify_multi_crossing
from src.io import load_legacy_512_snapshot
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
data=read(out/'step_8_5_m1_6_probe_summary.json')
routes={r['id']:deserialize_plot(r) for r in read(root/'outputs/step_8_5_legacy_512_plot_geometry.json')['routes']}
legacy=root.parent/'自动排布/AutoRouter'
ws={w.id:w for w in load_legacy_512_snapshot(legacy/'fiberBoard512.xlsx',legacy/'fiberBoard0data.xlsx')}
grid=build_track_grid_2d(TrackPolicyConfig(150.,.05,.125,5.))
baseline={tuple(r['route_ids']) for r in [json.loads(s) for s in (root/'outputs/step_8_5_legacy_512_multi_crossings.jsonl').read_text().splitlines()]}
results=[]
for c in data['cases']:
    if not c['best']:continue
    start=perf_counter();rid=c['victim'];index=c['best']['track_index'];w=ws[rid]
    sk=generate_assigned_routes_2d([w],[prepare_waveguide_2d(w,150.,0.)],[TrackAssignment(rid,'assigned',index,grid[index],None)],top_y=150.,bottom_y=0.)[0]
    candidate=smooth_orthogonal_route_2d(sk,5.)
    assert not find_smoothed_route_self_intersections_2d(candidate)
    star={s:find_physical_route_intersections_2d(candidate,routes[s]) for s in routes if s!=rid}
    assert not any(e.kind!='cross' for v in star.values() for e in v)
    found=set();checks=0
    for a,b in combinations(sorted(star),2):
        ac=[e for e in star[a] if e.kind=='cross'];bc=[e for e in star[b] if e.kind=='cross']
        if len(ac)!=1 or len(bc)!=1:continue
        ab=find_physical_route_intersections_2d(routes[a],routes[b]);checks+=1
        ab=[e for e in ab if e.kind=='cross']
        if len(ab)!=1:continue
        p={(a,b):ab,tuple(sorted((a,rid))):ac,tuple(sorted((b,rid))):bc}
        t=tuple(sorted((rid,a,b)))
        if classify_multi_crossing(t,p).classification=='multi_waveguide_crossing':found.add(t)
    old={t for t in baseline if rid in t}
    assert sorted(old-found)==[tuple(t) for t in c['best']['removed']]
    assert sorted(found-old)==[tuple(t) for t in c['best']['added']]
    assert 318-len(old)+len(found)==c['best']['M_after']<318
    assert tuple(c['target']) not in found
    results.append(dict(multi_id=c['multi_id'],victim=rid,star_pairs=511,fresh_fixed_pairs=checks,
        containing_victim_triples_considered=130305,M_after=318-len(old)+len(found),
        status='PASS',seconds=perf_counter()-start))
    print(results[-1],flush=True)
(out/'step_8_5_m1_6_independent_validation.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
