
import sys, json, time
sys.path.insert(0,r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D'); sys.path.insert(0,r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D\\scripts')
from copy import deepcopy
from pathlib import Path
from src.models import Layer, Point3D
from src.geometry_3d import lift_smoothed_route_to_layer
from src.multi_attribution import deserialize_plot
from src.fixed_1024_routing import deserialize_route3d, serialize_route3d
from src.three_layer_assignment_3d import LayerConfiguration
from src.overnight_engine_3d import run_strategy, StrategySpec
import overnight_registry as R
root=Path(r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D')
plot=json.loads((root/'outputs/step_8_5_legacy_512_plot_geometry.json').read_text(encoding='utf-8'))
planar={r['id']: lift_smoothed_route_to_layer(deserialize_plot(r),Layer(0,0)) for r in plot['routes']}
crossings={}
for text in (root/'outputs/step_8_5_legacy_512_physical_events.jsonl').read_text().splitlines():
    e=json.loads(text)
    if e['kind']=='cross':
        crossings.setdefault(tuple(sorted((e['route_a_id'],e['route_b_id']))),[]).append(Point3D(e['point']['x'],e['point']['y'],0))
d=root/R.MAIN_START
routes={row['route_id']: deserialize_route3d(row['geometry']) for row in json.loads((d/'final_routes.json').read_text(encoding='utf-8'))['routes']}
sets=json.loads((d/'collision_sets.json').read_text(encoding='utf-8'))
cfg=LayerConfiguration([Layer(0,0.),Layer(1,1.),Layer(2,2.)],R.CLEARANCE_MM,R.REQUIRED_RADIUS_MM,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC')
spec=R.p4_specs()['A_FAMILY_CAP24']
print('spec',spec.as_dict())
t0=time.perf_counter()
res=run_strategy({i:deepcopy(r) for i,r in routes.items()},planar,cfg,mode='R',appended_candidate_budget=200,
    spec=spec,saved_crossings=crossings,initial_pairs={tuple(p) for p in sets['final_collision_pairs']},
    initial_uncertain={tuple(p) for p in sets['final_unresolved_pairs']},generation_failure_cache=True)
print('elapsed',round(time.perf_counter()-t0,1))
L=res['ledger']
for k in ('final_collision_pair_count','candidate_evaluations','executed_moves','stop_reason','stage_length_cap_rejections','stage_length_cap_checks','stage_length_cap_rejected_step_length_mm','stage_length_cap_headroom_mm','stage_length_cap_rejected_step_length_mm','stage_length_delta_mm',
          'generation_accounting','candidates_by_window_kind','evaluated_candidates_by_window_kind',
          'full_accepted_candidates_by_window_kind','executed_moves_by_window_kind',
          'final_path_window_transition_count','final_logical_ramp_count','final_physical_fragment_count',
          'stage_length_cap_mm','basic_rejection_reason_counts','full_rejection_reason_counts'):
    print(k,'=',json.dumps(L[k],default=str)[:400])
# serialization / recheck of the new terminal route
n=0
for i,r in res['routes'].items():
    if r!=routes[i]:
        n+=1
        rr=deserialize_route3d(serialize_route3d(r))
        assert rr==r, i
print('changed routes',n,'round-trip ok')
