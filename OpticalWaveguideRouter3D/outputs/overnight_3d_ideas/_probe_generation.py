import sys, json
from pathlib import Path
sys.path.insert(0, ".")
from src.models import Layer
from src.geometry_3d import lift_smoothed_route_to_layer, CosineTransition3D
from src.multi_attribution import deserialize_plot
from src.fixed_1024_routing import deserialize_route3d
from src.sequential_elevation_3d import RouteView, pair_status
from src.three_layer_assignment_3d import LayerConfiguration, candidate_families
from src.models import Layer as L
from src.clearance_3d import analyze_route3d_clearance
from src.strategy_v2_3d import route_degrees, target_priority, target_points_for
root = Path(".")
plot = root/"outputs/step_8_5_legacy_512_plot_geometry.json"
ev = root/"outputs/step_8_5_legacy_512_physical_events.jsonl"
planar = {r["id"]: lift_smoothed_route_to_layer(deserialize_plot(r), Layer(0,0)) for r in json.loads(plot.read_text())["routes"]}
crossings = {}
from src.models import Point3D
for t in ev.read_text().splitlines():
    e = json.loads(t)
    if e["kind"]=="cross":
        crossings.setdefault(tuple(sorted((e["route_a_id"], e["route_b_id"]))), []).append(Point3D(e["point"]["x"], e["point"]["y"], 0))
cfg = LayerConfiguration([L(0,0.),L(1,1.),L(2,2.)], 0.1, 5.0, "LINE_ONLY_FINITE_WINDOWS", "EXPERIMENTAL_SYNTHETIC")
for kind, rel in (("main","outputs/3d_strategy_v3/512_ablation/D_both_enabled"), ("challenge","outputs/3d_strategy_v4/512_full_layout/N2880")):
    d = root/rel
    routes = {r["route_id"]: deserialize_route3d(r["geometry"]) for r in json.loads((d/"final_routes.json").read_text(encoding="utf-8"))["routes"]}
    sets = json.loads((d/"collision_sets.json").read_text(encoding="utf-8"))
    pairs = {tuple(p) for p in sets["final_collision_pairs"]}
    elevated = {i for i,r in routes.items() if any(isinstance(p,CosineTransition3D) for p in r.primitives)}
    deg = route_degrees(pairs)
    ordered = sorted(pairs, key=lambda p: target_priority(p, deg))
    print("==", kind, "elevated", len(elevated))
    for target in ordered[:6]:
        order = sorted(target, key=lambda r: (deg.get(r,0), r))
        print(" target", target, "deg", [deg.get(r,0) for r in order], "saved_cross", target in crossings, "elev", [r in elevated for r in order])
        for moved in order:
            other = target[1] if moved==target[0] else target[0]
            rep = analyze_route3d_clearance(routes[moved], routes[other], 0.1)
            pts = target_points_for(rep, crossings.get(target))
            try:
                cands, fail = candidate_families(planar[moved], target, pts, cfg, window_slack_mm=1e-5)
                print("     moved", moved, "status", rep["status"], "anchors", len(pts), "cands", len(cands), "fail", fail)
            except ValueError as ex:
                print("     moved", moved, "status", rep["status"], "anchors", len(pts), "EXC", ex)
