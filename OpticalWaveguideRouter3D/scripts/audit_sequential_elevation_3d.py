"""Consistency audit and deterministic replay of the same bounded 30 targets."""
import sys,json
from pathlib import Path
from itertools import combinations
from dataclasses import asdict
from time import perf_counter
ROOT=Path(sys.argv[1]).resolve();SOURCE=Path(sys.argv[2]).resolve();OUT=Path(sys.argv[3]).resolve()
sys.path.insert(0,str(ROOT))
from src.models import Layer,Point3D
from src.geometry_3d import (LineSegment3D,PlanarArcSegment3D,CosineTransition3D,Route3D,lift_smoothed_route_to_layer)
from src.layer_assignment_3d import LayerConfiguration
from src.multi_attribution import deserialize_plot
from src.sequential_elevation_3d import run_sequential_elevation,RouteView,pair_status
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

started=perf_counter()
summary=json.loads((OUT/'step_9_e_sequential_elevation_summary.json').read_text())
steps=json.loads((OUT/'step_9_e_target_attempts.json').read_text())
stored=json.loads((OUT/'step_9_e_final_route_state.json').read_text())
sets=json.loads((OUT/'step_9_e_collision_sets.json').read_text())
pool={tuple(p) for p in sets['initial_collision_pairs']};skipped=set()
for step in steps:
    target=tuple(step['target_pair'])
    assert target==min(pool-skipped)
    assert len(pool)==step['global_collision_pairs_before']
    if step['status']=='ELEVATED':
        moved=step['moved_route_id']
        for neighbor in step['old_collisions_removed']:pool.remove(tuple(sorted((moved,neighbor))))
        for neighbor in step['new_collisions_created']:pool.add(tuple(sorted((moved,neighbor))))
    else:skipped.add(target)
    assert len(pool)==step['global_collision_pairs_after']
assert pool=={tuple(p) for p in sets['final_collision_pairs']}
routes={r['route_id']:restore(r['geometry']) for r in stored['routes']}
views={i:RouteView.prepare(r) for i,r in routes.items()}
final=set();unknown=set()
for a,b in combinations(sorted(routes),2):
    s=pair_status(views[a],views[b],.1)
    if s=='COLLISION':final.add((a,b))
    elif s!='CLEAR':unknown.add((a,b))
assert final=={tuple(p) for p in sets['final_collision_pairs']}
assert unknown=={tuple(p) for p in sets['final_unresolved_pairs']}
print('Final collision set rebuilt and matched.',flush=True)
baseline={r['id']:lift_smoothed_route_to_layer(deserialize_plot(r),Layer(0,0)) for r in json.loads((SOURCE/'outputs/step_8_5_legacy_512_plot_geometry.json').read_text())['routes']}
baseline_views={i:RouteView.prepare(r) for i,r in baseline.items()}
crossings={}
for text in (SOURCE/'outputs/step_8_5_legacy_512_physical_events.jsonl').read_text().splitlines():
    e=json.loads(text)
    if e['kind']=='cross':crossings.setdefault(tuple(sorted((e['route_a_id'],e['route_b_id']))),[]).append(Point3D(e['point']['x'],e['point']['y'],0))
elevated=stored['elevated_route_ids']
checks=set(combinations(elevated,2))|{tuple(s['target_pair']) for s in steps}|unknown
for s in steps:
    if s['status']=='ELEVATED':checks.update(tuple(sorted((s['moved_route_id'],j))) for j in s['new_collisions_created'])
# Deterministic spread across canonical pairs, plus all final elevated/elevated
# pairs, every attempted target and every newly created collision pair.
allpairs=list(combinations(sorted(routes),2));checks.update(allpairs[::509])
direct=[]
for a,b in sorted(checks):
    for label,current,prepared in (('INITIAL',baseline,baseline_views),('FINAL',routes,views)):
        fast=pair_status(prepared[a],prepared[b],.1)
        full=analyze_route3d_clearance(current[a],current[b],.1)['status']
        assert fast==full,(label,a,b,fast,full)
        direct.append(dict(state=label,pair=[a,b],status=full))
print('Full 9-C API comparison passed:',len(direct),flush=True)
replay=run_sequential_elevation(baseline,LayerConfiguration([Layer(0,0),Layer(1,1)],.1,5.,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC'),max_targets=30,saved_crossings=crossings)
assert json.loads(json.dumps(replay['steps']))==steps
assert replay['routes']==routes
assert replay['final_collision_pairs']==sorted(final)
report=dict(status='PASS',final_all_pair_rebuild_count=len(allpairs),final_collision_count=len(final),
    final_unresolved_count=len(unknown),full_9c_comparison_count=len(direct),full_9c_comparisons=direct,
    deterministic_30_target_replay=True,all_step_records_equal=True,all_512_final_routes_equal=True,
    canonical_current_target_order_verified=True,
    incremental_collision_set_matches_fresh_rebuild=True,seconds=perf_counter()-started)
(OUT/'step_9_e_consistency_checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='full_9c_comparisons'}),flush=True)
