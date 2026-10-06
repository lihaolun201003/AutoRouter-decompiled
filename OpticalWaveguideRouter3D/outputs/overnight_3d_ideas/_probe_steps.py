import sys, json
from pathlib import Path
sys.path.insert(0, ".")
from src.models import Layer as L, Point3D
from src.geometry_3d import lift_smoothed_route_to_layer, CosineTransition3D
from src.multi_attribution import deserialize_plot
from src.fixed_1024_routing import deserialize_route3d
from src.three_layer_assignment_3d import LayerConfiguration
from src.overnight_engine_3d import run_strategy, StrategySpec, elevation_state_class
root = Path(".")
planar = {r["id"]: lift_smoothed_route_to_layer(deserialize_plot(r), L(0,0))
          for r in json.loads((root/"outputs/step_8_5_legacy_512_plot_geometry.json").read_text())["routes"]}
crossings = {}
for t in (root/"outputs/step_8_5_legacy_512_physical_events.jsonl").read_text().splitlines():
    e = json.loads(t)
    if e["kind"]=="cross":
        crossings.setdefault(tuple(sorted((e["route_a_id"], e["route_b_id"]))), []).append(Point3D(e["point"]["x"], e["point"]["y"], 0))
cfg = LayerConfiguration([L(0,0.),L(1,1.),L(2,2.)], 0.1, 5.0, "LINE_ONLY_FINITE_WINDOWS", "EXPERIMENTAL_SYNTHETIC")
for kind, rel in (("challenge","outputs/3d_strategy_v4/512_full_layout/N2880"), ("main","outputs/3d_strategy_v3/512_ablation/D_both_enabled")):
    d = root/rel
    routes = {r["route_id"]: deserialize_route3d(r["geometry"]) for r in json.loads((d/"final_routes.json").read_text(encoding="utf-8"))["routes"]}
    sets = json.loads((d/"collision_sets.json").read_text(encoding="utf-8"))
    pairs = {tuple(p) for p in sets["final_collision_pairs"]}
    unknown = {tuple(p) for p in sets["final_unresolved_pairs"]}
    print("=====", kind)
    for policy in ("LEGACY","STRATIFIED"):
        spec = StrategySpec("dbg_"+policy, target_policy=policy, max_targets=8, window_slack_mm=1e-5)
        res = run_strategy({i: r for i,r in routes.items()}, planar, cfg, mode="N",
                           appended_candidate_budget=10**9, spec=spec, saved_crossings=crossings,
                           initial_pairs=pairs, initial_uncertain=unknown)
        print(" policy", policy, "steps", len(res["steps"]), "moves", res["ledger"]["accepted_moves"],
              "final", res["ledger"]["final_collision_pair_count"])
        for s in res["steps"]:
            print("   step", s["step_index"], s["status"], "class", s["elevation_state_class"],
                  "target", s["target_pair"], "gen", [(va["route_id"], va.get("generated_count"), str(va.get("generation_failure"))[:70]) for va in s["victim_attempts"]])
