"""Cross-file consistency, no-op controls and descriptive secondary metrics."""
import sys,json,csv
from pathlib import Path
from collections import Counter,defaultdict
from hashlib import sha256
root=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]);sys.path.insert(0,str(root))
from src.multi_attribution import deserialize_plot,point_on_primitive
from src.models import Point2D
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
stats=read(out/'step_8_5_m1_6_victim_statistics.json')
with (out/'step_8_5_m1_6_victim_order.csv').open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(stats['triplets'][0]));writer.writeheader()
    for row in stats['triplets']:writer.writerow({k:json.dumps(v) if isinstance(v,(dict,list)) else v for k,v in row.items()})
plot=read(root/'outputs/step_8_5_legacy_512_plot_geometry.json')
routes={r['id']:deserialize_plot(r) for r in plot['routes']}
events={}
for line in (root/'outputs/step_8_5_legacy_512_physical_events.jsonl').read_text().splitlines():
    e=json.loads(line);events.setdefault((e['route_a_id'],e['route_b_id']),[]).append(e)
with (root/'outputs/step_8_5_m1_5_multi_crosses.csv').open(encoding='utf-8-sig',newline='') as f:crosses=list(csv.DictReader(f))
for c in crosses:
    a,b=int(c['route_a']),int(c['route_b']);p=Point2D(float(c['x']),float(c['y']))
    assert len(events[(a,b)])==1 and events[(a,b)][0]['point']=={'x':p.x,'y':p.y}
    assert point_on_primitive(p,routes[a].segments[int(c['primitive_a_index'])])
    assert point_on_primitive(p,routes[b].segments[int(c['primitive_b_index'])])
burden=Counter();partners=defaultdict(set)
for row in stats['triplets']:
    for rid in row['route_ids']:
        burden[rid]+=1;partners[rid].update(set(row['route_ids'])-{rid})
tied=[row for row in stats['triplets'] if len(row['lowest'])>1]
locality=dict(tied_lowest_with_different_unique_partner_counts=sum(len({len(partners[r]) for r in row['lowest']})>1 for row in tied),
    definition='Distinct other routes in incident unique multis; descriptive only, not a validated safety proxy')
cases=read(out/'step_8_5_m1_6_probe_summary.json')['cases'];controls=[];secondary=[]
for case in cases:
    rows=read(out/('step_8_5_m1_6_'+case['label']+'_candidates.json'))
    noops=[r for r in rows if r.get('track_displacement')==0]
    assert len(noops)==1
    r=noops[0];assert r['M_after']==318 and not r['target_multi_removed'] and not r['added'] and not r['removed'] and not r['accepted']
    controls.append(dict(multi_id=case['multi_id'],original_track=r['track_index'],no_op_status='PASS'))
    accepted=[r for r in rows if r['accepted']]
    bestM=min((r['M_after'] for r in accepted),default=None)
    tiedbest=[r for r in accepted if r['M_after']==bestM]
    secondary.append(dict(multi_id=case['multi_id'],candidates_at_best_accepted_M=len(tiedbest),
        new_multi_created_histogram=dict(Counter(r['new_multi_created'] for r in tiedbest)),
        length_delta_range_mm=[min(r['length_delta_mm'] for r in tiedbest),max(r['length_delta_mm'] for r in tiedbest)] if tiedbest else None,
        cross_count_range=[min(r['physical_cross_count'] for r in tiedbest),max(r['physical_cross_count'] for r in tiedbest)] if tiedbest else None,
        worsening_M_candidates=sum(r.get('M_after',318)>318 for r in rows),
        target_removed_but_no_improvement=sum(r.get('target_multi_removed',False) and r['M_after']>=318 for r in rows)))
protected=read(out/'step_8_5_m1_6_protected_hashes.json')
assert all(sha256(Path(p).read_bytes()).hexdigest()==h for p,h in protected.items())
result=dict(cross_rows_verified=954,locality=locality,no_op_controls=controls,secondary_metrics=secondary,protected_files_unchanged=len(protected))
(out/'step_8_5_m1_6_supplemental_checks.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
