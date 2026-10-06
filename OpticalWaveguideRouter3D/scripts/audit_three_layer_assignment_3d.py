"""Rebuild counts, compare full 9-C classifications and replay both 50-target runs."""
import sys,json
from pathlib import Path
from itertools import combinations
from copy import deepcopy
from time import perf_counter
ROOT=Path(sys.argv[1]).resolve();SOURCE=Path(sys.argv[2]).resolve();OUT=Path(sys.argv[3]).resolve()
sys.path.insert(0,str(ROOT))
from src.models import Layer,Point3D
from src.geometry_3d import LineSegment3D,PlanarArcSegment3D,CosineTransition3D,Route3D,lift_smoothed_route_to_layer
from src.multi_attribution import deserialize_plot
from src.sequential_elevation_3d import RouteView,pair_status,collision_degree,victim_order
from src.three_layer_assignment_3d import LayerConfiguration,run_layer_assignment_probe
from src.clearance_3d import analyze_route3d_clearance

def restore(data):
    pieces=[]
    for raw in data['primitives']:
        if 'radius' in raw:
            p=PlanarArcSegment3D(raw['center_x'],raw['center_y'],raw['z'],raw['radius'],raw['start_angle'],raw['sweep_angle'])
            for key in ('_source_start_xy','_source_end_xy'):
                if raw.get(key) is not None:object.__setattr__(p,key,tuple(raw[key]))
        else:
            a,b=Point3D(**raw['start']),Point3D(**raw['end'])
            p=LineSegment3D(a,b) if a.z==b.z else CosineTransition3D(a,b)
        pieces.append(p)
    return Route3D(data['route_id'],pieces,data['continuity_tol'])
def read(name):return json.loads((OUT/name).read_text())
def save(data):(OUT/'step_9_f_consistency_checks.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
started=perf_counter()
baseline={r['id']:lift_smoothed_route_to_layer(deserialize_plot(r),Layer(0,0)) for r in json.loads((SOURCE/'outputs/step_8_5_legacy_512_plot_geometry.json').read_text())['routes']}
crossings={}
for text in (SOURCE/'outputs/step_8_5_legacy_512_physical_events.jsonl').read_text().splitlines():
    e=json.loads(text)
    if e['kind']=='cross':crossings.setdefault(tuple(sorted((e['route_a_id'],e['route_b_id']))),[]).append(Point3D(e['point']['x'],e['point']['y'],0))
audit={}
for label,n in (('two_layer',2),('three_layer',3)):
    steps=read(f'step_9_f_{label}_attempts.json');sets=read(f'step_9_f_{label}_collision_sets.json')
    stored=read(f'step_9_f_{label}_final_route_state.json')
    routes={r['route_id']:restore(r['geometry']) for r in stored['routes']};views={i:RouteView.prepare(r) for i,r in routes.items()}
    pool={tuple(p) for p in sets['initial_collision_pairs']};skipped=set();moved_ids=set();families_checked=0
    for s in steps:
        target=tuple(s['target_pair']);assert target==min(pool-skipped)
        assert s['victim_order']==victim_order(target,pool)
        assert len(pool)==s['global_collision_pairs_before']
        for va in s['victim_attempts']:
            if va['status']=='ROUTE_ALREADY_ELEVATED':assert va['route_id'] in moved_ids;continue
            assert set(map(int,va['generation_failure']))==set(range(1,n))
            for row in va['candidates']:
                if row['basic_status']=='ACCEPTED_TARGET_PAIR_ONLY':
                    assert row['checked_neighbor_count']==511
                    assert row['current_elevated_neighbors_checked']==sorted(moved_ids)
            families_checked+=n-1
        if s['status']=='ELEVATED':
            moved=s['moved_route_id'];assert moved not in moved_ids;moved_ids.add(moved)
            va=next(v for v in s['victim_attempts'] if v['status']=='SELECTED')
            eligible=[r for r in va['candidates'] if r.get('status')=='IMPROVING']
            rank=lambda r:(r['after_collision_count'],len(r['new_collisions_created']),r['extra_length_mm'],r['elevated_length_mm'],r['target_layer_id'],r['rise_window'],r['fall_window'])
            best=min(eligible,key=rank)
            assert best['candidate_index']==s['selected_candidate_index'] and best['target_layer_id']==s['target_layer_id']
            for j in s['old_collisions_removed']:pool.remove(tuple(sorted((moved,j))))
            for j in s['new_collisions_created']:pool.add(tuple(sorted((moved,j))))
            assert s['global_collision_pairs_before']-len(pool)==s['net_collision_reduction']>0
        else:skipped.add(target)
        assert len(pool)==s['global_collision_pairs_after']
    assert pool=={tuple(p) for p in sets['final_collision_pairs']}
    if label=='two_layer':
        normalized=deepcopy(steps[:30])
        for s in normalized:
            s.pop('target_layer_id',None)
            for va in s['victim_attempts']:
                if 'generation_failure' in va:va['generation_failure']=va['generation_failure']['1']
                for r in va['candidates']:r.pop('target_layer_id',None)
        old=json.loads((SOURCE/'outputs/step_9_e_target_attempts.json').read_text())
        assert normalized==old
    final=set();unknown=set();allpairs=list(combinations(sorted(routes),2))
    for a,b in allpairs:
        status=pair_status(views[a],views[b],.1)
        if status=='COLLISION':final.add((a,b))
        elif status!='CLEAR':unknown.add((a,b))
    assert final==pool and unknown=={tuple(p) for p in sets['final_unresolved_pairs']}
    print(label,'final full-pair rebuild matched',len(final),flush=True)
    checks=set(combinations(sorted(moved_ids),2))|{tuple(s['target_pair']) for s in steps}|set(allpairs[::1021])|unknown
    direct=[]
    for a,b in sorted(checks):
        full=analyze_route3d_clearance(routes[a],routes[b],.1)['status']
        fast=pair_status(views[a],views[b],.1);assert full==fast,(label,a,b,full,fast)
        direct.append(dict(pair=[a,b],status=full))
    print(label,'full 9-C API matched',len(direct),'replaying same 50 targets',flush=True)
    config=LayerConfiguration([Layer(i,float(i)) for i in range(n)],.1,5.,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC')
    replay=run_layer_assignment_probe(baseline,config,max_targets=50,saved_crossings=crossings)
    assert json.loads(json.dumps(replay['steps']))==steps and replay['routes']==routes
    audit[label]=dict(status='PASS',target_attempts=50,canonical_order_verified=True,victim_order_verified=True,
        all_generated_legal_candidates_evaluated=True,families_checked=families_checked,unified_layer_ranking_verified=True,
        current_elevated_neighbors_verified=True,once_per_route=True,full_pair_rebuild_count=len(allpairs),
        final_collision_count=len(final),full_9c_comparison_count=len(direct),full_9c_comparisons=direct,
        deterministic_50_target_replay=True,final_512_route_equality=True,
        historical_9e_first_30_unchanged=True if n==2 else None)
    save(dict(status='IN_PROGRESS',experiments=audit,seconds=perf_counter()-started))
    print(label,'audit complete',flush=True)
save(dict(status='PASS',experiments=audit,seconds=perf_counter()-started))
