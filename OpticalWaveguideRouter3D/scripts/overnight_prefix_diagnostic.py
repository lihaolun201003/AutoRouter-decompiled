"""v6 diagnostic 3: does the fixed K prefix lose a better candidate than full
enumeration would have found?

Frozen before any v6 run: the 120 (target, moved-side) entries of the step-17
audit list outputs/3d_strategy_v4/512_full_layout/audit/side_audit.json, which was
saved BEFORE any v4 candidate evaluation. The list is used only as a fixed
diagnostic sample; it never selects a performance target and its cost is booked
separately from every optimisation budget.

For each frozen side the script evaluates candidates in the SAME cheap order the
v6 E2 policy uses (unified cheap score), then reports
   exhaustive winner  = best strategy_rank among fully accepted, over everything
   K-prefix winner    = best strategy_rank among fully accepted, inside the first K
   net reduction difference, and whether the prefix lost the best candidate.
This is a prefix-vs-full comparison on a fixed diagnostic set, NOT a whole-board
optimality guarantee for either policy.

Usage: .venv\\Scripts\\python.exe -B scripts\\overnight_prefix_diagnostic.py PROJECT OUTDIR [--k 16]
"""
import sys, json, argparse
from pathlib import Path
from collections import Counter
from time import perf_counter


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("project"); ap.add_argument("outdir")
    ap.add_argument("--k", type=int, default=16)
    ap.add_argument("--start", default="outputs/3d_strategy_v3/512_ablation/D_both_enabled")
    ap.add_argument("--basic-cap", type=int, default=400)
    ap.add_argument("--full-cap", type=int, default=60)
    args = ap.parse_args(sys.argv[1:])
    root = Path(args.project).resolve(); out = Path(args.outdir).resolve()
    sys.path.insert(0, str(root))
    from src.models import Layer as L, Point3D
    from src.geometry_3d import lift_smoothed_route_to_layer, CosineTransition3D
    from src.multi_attribution import deserialize_plot
    from src.fixed_1024_routing import deserialize_route3d
    from src.three_layer_assignment_3d import LayerConfiguration, candidate_families
    from src.layer_assignment_3d import evaluate_elevation
    from src.clearance_3d import analyze_route3d_clearance
    from src.sequential_elevation_3d import RouteView
    from src.strategy_v2_3d import (route_degrees, target_points_for, strategy_rank,
                                    full_acceptance)
    from src.overnight_engine_3d import cheap_candidate_score, geometry_fingerprint

    planar = {r["id"]: lift_smoothed_route_to_layer(deserialize_plot(r), L(0, 0))
              for r in json.loads((root / "outputs/step_8_5_legacy_512_plot_geometry.json").read_text())["routes"]}
    crossings = {}
    for text in (root / "outputs/step_8_5_legacy_512_physical_events.jsonl").read_text().splitlines():
        e = json.loads(text)
        if e["kind"] == "cross":
            crossings.setdefault(tuple(sorted((e["route_a_id"], e["route_b_id"]))), []).append(
                Point3D(e["point"]["x"], e["point"]["y"], 0))
    cfg = LayerConfiguration([L(0, 0.), L(1, 1.), L(2, 2.)], 0.1, 5.0,
                             "LINE_ONLY_FINITE_WINDOWS", "EXPERIMENTAL_SYNTHETIC")
    start_dir = root / args.start
    routes = {r["route_id"]: deserialize_route3d(r["geometry"])
              for r in json.loads((start_dir / "final_routes.json").read_text(encoding="utf-8"))["routes"]}
    sets = json.loads((start_dir / "collision_sets.json").read_text(encoding="utf-8"))
    pairs = {tuple(p) for p in sets["final_collision_pairs"]}
    elevated = {i for i, r in routes.items() if any(isinstance(p, CosineTransition3D)
                                                     for p in r.primitives)}
    degrees = route_degrees(pairs)
    views = {i: RouteView.prepare(r) for i, r in routes.items()}
    audit = json.loads((root / "outputs/3d_strategy_v4/512_full_layout/audit/side_audit.json")
                       .read_text(encoding="utf-8"))["records"]
    ledger = Counter(); rows = []
    started = perf_counter()
    for record in audit:
        target = tuple(record["target_pair"]); moved = record["moved_route_id"]
        other = record["other_route_id"]
        for key in ("basic_evaluations", "full_checks"):
            ledger[key + "_in_v4_audit_reference"] += record.get(key, 0)
        # Every one of the 120 frozen sides is evaluated, exactly as the step-17 audit
        # did; the prefix question is about candidate ORDER, not movement permission.
        report = analyze_route3d_clearance(routes[moved], routes[other], cfg.clearance_mm)
        points = target_points_for(report, crossings.get(target))
        try:
            candidates, failure = candidate_families(planar[moved], target, points, cfg,
                                                     window_slack_mm=1e-5)
        except ValueError as ex:
            candidates, failure = [], str(ex)
        pool = sorted(range(len(candidates)),
                      key=lambda i: cheap_candidate_score(moved, i, candidates[i], other, degrees))
        old_neighbors = {b if a == moved else a for a, b in pairs if moved in (a, b)}
        current_length = routes[moved].total_length()
        evaluated = []; accepted = []
        side_basic = side_full = 0
        for order_index, i in enumerate(pool):
            if side_basic >= args.basic_cap:
                ledger["basic_evaluations_skipped_by_cap"] += len(pool) - order_index; break
            cand = candidates[i]; ledger["basic_evaluations"] += 1; side_basic += 1
            basic = evaluate_elevation(cand, routes[moved], routes[other], cfg)
            entry = dict(candidate_index=i, order_index=order_index, basic_status=basic["status"])
            evaluated.append(entry)
            if basic["status"] != "ACCEPTED_TARGET_PAIR_ONLY":
                continue
            if side_full >= args.full_cap:
                ledger["full_checks_skipped_by_cap"] += 1; entry["full_status"] = "SKIPPED_BY_CAP"; continue
            full, _ = full_acceptance(cand, moved, planar[moved], current_length, views,
                                      old_neighbors, cfg)
            ledger["full_checks"] += 1; side_full += 1; entry.update(full)
            if full["status"] == "ACCEPTED_FULL":
                accepted.append(dict(order_index=order_index, net=full["net_collision_reduction"],
                                     row={**full, "candidate": cand, "victim_id": moved}))
        exhaustive = min(accepted, key=lambda a: strategy_rank(a["row"])) if accepted else None
        prefix = [a for a in accepted if a["order_index"] < args.k]
        prefix_best = min(prefix, key=lambda a: strategy_rank(a["row"])) if prefix else None
        rows.append(dict(target_pair=list(target), moved_route_id=moved,
                         generated=len(candidates), raw_failure=failure,
                         cheap_order_used=True, evaluated=len(evaluated),
                         full_accepted=len(accepted),
                         exhaustive_winner_net=(exhaustive["net"] if exhaustive else None),
                         k_prefix_winner_net=(prefix_best["net"] if prefix_best else None),
                         prefix_lost_better=(exhaustive is not None and
                                             (prefix_best is None or exhaustive["net"] > prefix_best["net"]))))
    measured = [r for r in rows if r.get("evaluated", 0) > 0 and r.get("full_accepted") is not None]
    lost = [r for r in measured if r["prefix_lost_better"]]
    doc = dict(k=args.k, start_state=args.start, basic_cap_per_side=args.basic_cap,
               full_cap_per_side=args.full_cap,
               frozen_diagnostic_set=("outputs/3d_strategy_v4/512_full_layout/audit/side_audit.json ",
                                      "(120 sides, saved before any v4 candidate evaluation)"),
               accounting=dict(ledger),
               sides_measured=len(measured), sides_with_any_full_accept=sum(
                   1 for r in measured if r["full_accepted"]),
               sides_where_prefix_lost_a_better_or_equal_candidate=len(lost),
               total_exhaustive_net=sum(r["exhaustive_winner_net"] or 0 for r in measured),
               total_prefix_net=sum(r["k_prefix_winner_net"] or 0 for r in measured),
               claim_limit=("a fixed-diagnostic-set prefix-versus-full comparison; it is NOT a "
                            "whole-board optimality guarantee for either policy"),
               seconds=perf_counter() - started, rows=rows)
    out.mkdir(parents=True, exist_ok=True)
    (out / "v6_prefix_diagnostic.json").write_text(json.dumps(doc, indent=2, default=str),
                                                   encoding="utf-8")
    print(json.dumps({k: v for k, v in doc.items() if k != "rows"}, indent=2, default=str))


if __name__ == "__main__":
    main()
