import sys, json
sys.path.insert(0, r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D')
from src.models import Layer, Point3D
from src.geometry_3d import LineSegment3D, Route3D, CosineTransition3D
from src.geometry_3d_diagnostics import minimum_xy_run_for_radius
from src.clearance_3d import analyze_route3d_clearance
from src.sequential_elevation_3d import RouteView, pair_status
from src.three_layer_assignment_3d import LayerConfiguration
from src.layer_assignment_3d import build_elevation_candidate, elevation_candidates
from src.strategy_v4_3d import run_full_layout_v4, elevation_structure

cfg = LayerConfiguration([Layer(0,0.),Layer(1,1.),Layer(2,2.)],.1,5.,'LINE_ONLY_FINITE_WINDOWS','EXPERIMENTAL_SYNTHETIC')
def L(a,b): return LineSegment3D(Point3D(*a), Point3D(*b))

plan0 = Route3D(0, [L((-50,0,0),(50,0,0))])
plan1 = Route3D(1, [L((0,-50,0),(0,50,0))])
print('run z=1', minimum_xy_run_for_radius(1.,5.), 'len', plan0.total_length())
run1 = minimum_xy_run_for_radius(1.,5.)*(1+1e-6)/100.
run2 = minimum_xy_run_for_radius(2.,5.)*(1+1e-6)/100.

# route 0 elevated to layer 1 with transitions near its ends
c0 = build_elevation_candidate(plan0,(0,1),[Point3D(0,0,0)],cfg,(0,0.01,0.01+run1),(0,0.94,0.99),target_layer_id=1)
# route 1 elevated to layer 1 with transitions straddling the centre
c1 = build_elevation_candidate(plan1,(0,1),[Point3D(0,0,0)],cfg,(0,0.40,0.40+run1),(0,0.55,0.60),target_layer_id=1)
start = {0: c0.route, 1: c1.route}
print('structure', elevation_structure(c0.route), elevation_structure(c1.route))
views = {i: RouteView.prepare(r) for i,r in start.items()}
print('pair status layer1/layer1:', pair_status(views[0],views[1],.1))
print('transitions', [type(p).__name__ for p in start[0].primitives])
print('transitions r1', [type(p).__name__ for p in start[1].primitives])

for mode in ('N','R'):
    r = run_full_layout_v4(start, {0:plan0,1:plan1}, cfg, mode=mode, appended_candidate_budget=200, max_targets=5)
    led = r['ledger']
    print(mode, 'final', led['final_collision_pair_count'], 'moves', led['accepted_moves'],
          'reloc', led['relocations'], 'evals', led['candidate_evaluations'],
          'stop', led['stop_reason'], 'skip(no movable)', led['no_movable_route_skip_events'],
          'reloc_evals', led['relocation_candidate_evaluations'])
    print('   steps', [(s['target_pair'], s['status'], s.get('movement')) for s in r['steps']])
    if led['relocations']:
        st = [s for s in r['steps'] if s['status']=='RELOCATED'][0]
        print('   reloc step delta', st['step_length_delta_mm'], 'layer', st['target_layer_id'],
              'structure', elevation_structure(r['routes'][st['moved_route_id']]))
