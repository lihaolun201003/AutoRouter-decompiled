"""How deep is the run of structurally impossible targets at the top of the
priority order, from each start state? Pure generation, no acceptance, no
budget. This is a diagnostic only and is booked separately."""
import sys, json
from pathlib import Path
sys.path.insert(0, ".")
from src.models import Layer as L, Point3D
from src.geometry_3d import lift_smoothed_route_to_layer, CosineTransition3D
from src.multi_attribution import deserialize_plot
from src.fixed_1024_routing import deserialize_route3d
from src.three_layer_assignment_3d import LayerConfiguration, candidate_families
from src.clearance_3d import analyze_route3d_clearance
from src.strategy_v2_3d import route_degrees, target_priority, target_points_for
root = Path(".")
planar = {r["id"]: lift_smoothed_route_to_layer(deserialize_plot(r), L(0,0))
          for r in json.loads((root/"outputs/step_8_5_legacy_512_plot_geometry.json").read_text())["routes"]}
crossings = {}
for t in (root/"outputs/step_8_5_legacy_512_physical_events.jsonl").read_text().splitlines():
    e = json.loads(t)
    if e["kind"]=="cross":
        crossings.setdefault(tuple(sorted((e["route_a_id"], e["route_b_id"]))), []).append(Point3D(e["point"]["x"], e["point"]["y"], 0))
cfg = LayerConfiguration([L(0,0.),L(1,1.),L(2,2.)], 0.1, 5.0, "LINE_ONLY_FINITE_WINDOWS", "EXPERIMENTAL_SYNTHETIC")
LIMIT = 420
out = {}
for kind, rel in (("main","outputs/3d_strategy_v3/512_ablation/D_both_enabled"), ("challenge","outputs/3d_strategy_v4/512_full_layout/N2880")):
    d = root/rel
    routes = {r["route_id"]: deserialize_route3d(r["geometry"]) for r in json.loads((d/"final_routes.json").read_text(encoding="utf-8"))["routes"]}
    sets = json.loads((d/"collision_sets.json").read_text(encoding="utf-8"))
    pairs = {tuple(p) for p in sets["final_collision_pairs"]}
    elevated = {i for i,r in routes.items() if any(isinstance(p,CosineTransition3D) for p in r.primitives)}
    deg = route_degrees(pairs)
    ordered = sorted(pairs, key=lambda p: target_priority(p, deg))
    rows = []; first_productive = None; productive = 0
    for rank, target in enumerate(ordered[:LIMIT], start=1):
        best = 0; detail = []
        for moved in sorted(target, key=lambda r: (deg.get(r,0), r)):
            if moved in elevated:   # N mode: already elevated cannot move
                detail.append([moved, "ELEVATED_NOT_MOVABLE_IN_N", 0]); continue
            other = target[1] if moved==target[0] else target[0]
            rep = analyze_route3d_clearance(routes[moved], routes[other], 0.1)
            pts = target_points_for(rep, crossings.get(target))
            try:
                cands, fail = candidate_families(planar[moved], target, pts, cfg, window_slack_mm=1e-5)
                detail.append([moved, len(cands), str(fail)]); best = max(best, len(cands))
            except ValueError as ex:
                detail.append([moved, 0, str(ex)])
        if best > 0:
            productive += 1
            if first_productive is None: first_productive = rank
        rows.append(dict(rank=rank, target=list(target), state_class=("UU","UE","EE")[sum(1 for r in target if r in elevated)], best_generated=best, detail=detail))
    out[kind] = dict(elevated_routes=len(elevated), pairs=len(pairs), inspected=len(rows),
                     inspected_limit=LIMIT, productive_targets_in_limit=productive,
                     first_productive_rank=first_productive,
                     note=("generation-only diagnostic: candidate_families on the frozen planar route for the "
                           "victims movable in mode N, window_slack 1e-5, booked separately from any budget"))
    out[kind]["first_40"] = [{k: r[k] for k in ("rank","target","state_class","best_generated")} for r in rows[:40]]
    print(kind, out[kind]["inspected"], "productive", productive, "first_productive_rank", first_productive)
(root/"outputs/overnight_3d_ideas/diagnostics_target_depth.json").write_text(json.dumps(out, indent=2))
