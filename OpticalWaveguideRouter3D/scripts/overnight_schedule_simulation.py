"""Generation-only scheduling probe (DIAGNOSTIC, booked separately).

Replays the engine scheduling decision (target policy, structural zero-candidate
cache, failure cache) with the REAL generator but WITHOUT any acceptance, so it
answers a pure scheduling question cheaply: how many of the first N target
attempts produce at least one candidate, and where do the attempts land?
"""
import sys, json
from pathlib import Path
from collections import Counter, defaultdict
sys.path.insert(0, ".")
from src.models import Layer as L, Point3D
from src.geometry_3d import lift_smoothed_route_to_layer, CosineTransition3D
from src.multi_attribution import deserialize_plot
from src.fixed_1024_routing import deserialize_route3d
from src.three_layer_assignment_3d import LayerConfiguration, candidate_families
from src.clearance_3d import analyze_route3d_clearance
from src.strategy_v2_3d import (route_degrees, target_priority, target_points_for,
                                generation_input_key, generation_cache_hit)
root = Path(".")
planar = {r["id"]: lift_smoothed_route_to_layer(deserialize_plot(r), L(0,0))
          for r in json.loads((root/"outputs/step_8_5_legacy_512_plot_geometry.json").read_text())["routes"]}
crossings = {}
for t in (root/"outputs/step_8_5_legacy_512_physical_events.jsonl").read_text().splitlines():
    e = json.loads(t)
    if e["kind"]=="cross":
        crossings.setdefault(tuple(sorted((e["route_a_id"], e["route_b_id"]))), []).append(Point3D(e["point"]["x"], e["point"]["y"], 0))
cfg = LayerConfiguration([L(0,0.),L(1,1.),L(2,2.)], 0.1, 5.0, "LINE_ONLY_FINITE_WINDOWS", "EXPERIMENTAL_SYNTHETIC")
SLACK = 1e-5
def klass(p, elevated): return ("UU","UE","EE")[sum(1 for r in p if r in elevated)]
def run(kind, rel, policy, steps_n, mode="N"):
    d = root/rel
    routes = {r["route_id"]: deserialize_route3d(r["geometry"]) for r in json.loads((d/"final_routes.json").read_text(encoding="utf-8"))["routes"]}
    sets = json.loads((d/"collision_sets.json").read_text(encoding="utf-8"))
    pairs = {tuple(p) for p in sets["final_collision_pairs"]}
    elevated = {i for i,r in routes.items() if any(isinstance(p,CosineTransition3D) for p in r.primitives)}
    gen_records = {}; failure_cache = {}; layout_version = 0
    rows = []; route_touch = {i: -1 for i in routes}; first_seen = {}
    for step in range(1, steps_n+1):
        deg = route_degrees(pairs)
        pending = {p for p in pairs if failure_cache.get(p) != layout_version}
        for p in pending: first_seen.setdefault(p, step)
        target = None
        while pending:
            if policy == "STRATIFIED":
                grouped = defaultdict(list)
                for p in pending: grouped[klass(p, elevated)].append(p)
                ring = ("UU","UE","EE"); start = step % 3; pick = None
                for off in range(3):
                    b = grouped.get(ring[(start+off)%3])
                    if b: pick = min(b, key=lambda p: target_priority(p, deg)); break
                cand = pick
            else:
                cand = min(pending, key=lambda p: target_priority(p, deg))
            if cand is None: break
            movable = [r for r in cand if mode == "R" or r not in elevated]
            if not movable:
                pending.discard(cand); continue
            zero = all((cand,m) in gen_records and gen_records[(cand,m)][1] == 0 for m in movable)
            if zero:
                pending.discard(cand); continue
            target = cand; break
        if target is None:
            rows.append(dict(step=step, status="NO_ELIGIBLE_TARGETS")); break
        order = sorted(target, key=lambda r: (deg.get(r,0), r))
        per = []
        for moved in order:
            if moved in elevated and mode == "N":
                per.append([moved, None, "ELEVATED_NOT_MOVABLE_IN_N"]); continue
            other = target[1] if moved == target[0] else target[0]
            rep = analyze_route3d_clearance(routes[moved], routes[other], 0.1)
            pts = target_points_for(rep, crossings.get(target))
            try:
                cands, fail = candidate_families(planar[moved], target, pts, cfg, window_slack_mm=SLACK)
                n = len(cands); why = fail
            except ValueError as ex:
                n = 0; why = str(ex)
            gen_records[(target, moved)] = (generation_input_key(planar[moved], pts, cfg, window_slack_mm=SLACK), n)
            per.append([moved, n, str(why)])
        total = max([x[1] or 0 for x in per] or [0])
        rows.append(dict(step=step, target=list(target), state_class=klass(target, elevated),
                         generated=[x[1] for x in per], best=total,
                         reasons=[x[2] for x in per]))
        if total == 0:
            failure_cache[target] = layout_version
        else:
            layout_version += 1   # stand-in: a candidate exists, so the layout would change
            for r in target: route_touch[r] = step
    return dict(kind=kind, policy=policy, mode=mode, steps_recorded=len(rows),
                zero_candidate_steps=sum(1 for r in rows if r.get("best") == 0),
                productive_steps=sum(1 for r in rows if (r.get("best") or 0) > 0),
                state_class_histogram=dict(Counter(r.get("state_class") for r in rows if r.get("state_class"))),
                reason_histogram=dict(Counter(x for r in rows for x in r.get("reasons", []) if x)),
                first_20=rows[:20])
out = {}
for kind, rel in (("challenge","outputs/3d_strategy_v4/512_full_layout/N2880"), ("main","outputs/3d_strategy_v3/512_ablation/D_both_enabled")):
    for policy in ("LEGACY","STRATIFIED"):
        key = kind + "_" + policy
        out[key] = run(kind, rel, policy, 60)
        print(key, "zero_steps", out[key]["zero_candidate_steps"], "productive", out[key]["productive_steps"],
              "classes", out[key]["state_class_histogram"])
(root/"outputs/overnight_3d_ideas/diagnostics_schedule_simulation.json").write_text(json.dumps(out, indent=2))
