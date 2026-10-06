"""v8 frozen 60-pair / 120-side diagnostic (generation and acceptance only).

The target list and the side classification are the FROZEN v4 audit
(outputs/3d_strategy_v4/512_full_layout/audit/target_list.json and
side_audit.json, seed 20261006). This script answers, for the SAME 120 sides:

  * did G0 (line windows) produce candidates?
  * did G1 (path windows) produce candidates, and what did the extra windows do?
  * basic acceptance / full acceptance outcome of those candidates
  * for the 33 sides that had NO legal window under the old rules: do they get
    candidates now, do they pass basic and full acceptance, or are they still
    window-less / curvature-infeasible / undecided?

BOOKING: this diagnostic spends its own budget and is excluded from every
optimisation budget. It is never used to pick a performance target.

Usage:
  python -B scripts/v8_diagnostics.py PROJECT OUTDIR [--basic-cap 400] [--full-cap 60]
"""
import csv
import json
import sys
import time
from collections import Counter
from copy import deepcopy
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))

from src.fixed_1024_routing import deserialize_route3d
from src.geometry_3d import lift_smoothed_route_to_layer
from src.layer_assignment_3d import evaluate_elevation
from src.models import Layer, Point3D
from src.multi_attribution import deserialize_plot
from src.path_window_3d import candidate_path_offsets, planar_path_model
from src.sequential_elevation_3d import RouteView, pair_status
from src.strategy_v2_3d import full_acceptance, target_points_for
from src.three_layer_assignment_3d import LayerConfiguration, candidate_families
import overnight_registry as REG

AUDIT = ROOT / "outputs/3d_strategy_v4/512_full_layout/audit"
V4_START = ROOT / "outputs/3d_strategy_v4/512_full_layout/N2880"
BASIC_CAP = 400
FULL_CAP = 60
for i, arg in enumerate(sys.argv):
    if arg == "--basic-cap":
        BASIC_CAP = int(sys.argv[i + 1])
    if arg == "--full-cap":
        FULL_CAP = int(sys.argv[i + 1])

OUTCOMES = ("NO_LEGAL_WINDOW_UNDER_CURRENT_RULES",
            "CANDIDATES_EXIST_BASIC_ALL_REJECTED",
            "BASIC_PASSES_FULL_NO_NET_GAIN",
            "BASIC_PASSES_FULL_CHECK_CAPPED",
            "FULL_ACCEPTED_CANDIDATE_EXISTS")


def config():
    return LayerConfiguration([Layer(0, 0.), Layer(1, 1.), Layer(2, 2.)], REG.CLEARANCE_MM,
                              REG.REQUIRED_RADIUS_MM, "LINE_ONLY_FINITE_WINDOWS",
                              "EXPERIMENTAL_SYNTHETIC")


def load_planar_and_crossings():
    plot = json.loads((ROOT / "outputs/step_8_5_legacy_512_plot_geometry.json").read_text(encoding="utf-8"))
    planar = {r["id"]: lift_smoothed_route_to_layer(deserialize_plot(r), Layer(0, 0))
              for r in plot["routes"]}
    crossings = {}
    for text in (ROOT / "outputs/step_8_5_legacy_512_physical_events.jsonl").read_text().splitlines():
        e = json.loads(text)
        if e["kind"] == "cross":
            key = tuple(sorted((e["route_a_id"], e["route_b_id"])))
            crossings.setdefault(key, []).append(Point3D(e["point"]["x"], e["point"]["y"], 0))
    return planar, crossings


def side_report(planar, crossings, record, domain):
    """Generate, basically evaluate and (capped) fully check ONE side."""
    target = tuple(record["target_pair"])
    moved = record["moved_route_id"]
    other = record["other_route_id"]
    cfg = config()
    points = list(crossings.get(target, []))
    stats = {}
    report = dict(generation_domain=domain, moved_route_id=moved, other_route_id=other,
                  target_pair=list(target), saved_anchor_count=len(points))
    started = time.perf_counter()
    try:
        candidates, failures = candidate_families(planar[moved], target, points, cfg,
                                                  window_slack_mm=REG.WINDOW_SLACK_MM,
                                                  generation_domain=domain, stats_out=stats)
    except ValueError as ex:
        report.update(status="GENERATION_ERROR", detail=str(ex), candidates=0,
                      basic_passed=0, basic_evaluations=0, full_checks=0, full_passed=0,
                      generated_candidates=0, generated_path_windows=0, curvature_rejected=0)
        return report, dict(basic=0, full=0, seconds=time.perf_counter() - started)
    report["failures"] = {str(k): v for k, v in failures.items()}
    report["generation_stats"] = {k: v for k, v in stats.items() if k != "path_window_settings"}
    report["generated_candidates"] = len(candidates)
    report["generated_line_windows"] = stats.get("line_window_candidates", len(candidates))
    report["generated_path_windows"] = stats.get("path_window_candidates", 0)
    report["curvature_rejected"] = stats.get("path_window_curvature_rejected", 0)
    report["path_window_build_rejected"] = stats.get("path_window_build_rejected", 0)
    report["path_window_length_does_not_fit"] = sum(
        (stats.get("length_does_not_fit") or {}).values()) if isinstance(
            stats.get("length_does_not_fit"), dict) else stats.get("path_window_length_does_not_fit", 0)
    report["path_window_empty_legal_interval"] = any(
        (stats.get("no_legal_interval") or {}).values()) if isinstance(
            stats.get("no_legal_interval"), dict) else False
    if not candidates:
        report["status"] = "NO_LEGAL_WINDOW_UNDER_CURRENT_RULES"
        report["outcome"] = "NO_LEGAL_WINDOW_UNDER_CURRENT_RULES"
        report.update(basic_passed=0, basic_evaluations=0, basic_rejected=0, full_checks=0,
                      full_passed=0, full_check_capped=False)
        return report, dict(basic=0, full=0, seconds=time.perf_counter() - started)
    models = planar_path_model(planar[moved])
    if domain == "PATH_WINDOWS":
        line_keys = {(c.layer_to, candidate_path_offsets(models, c)) for c in candidates
                     if getattr(c, "window_kind", "LINE_WINDOW_G0") != "PATH_WINDOW_G1"}
        report["path_windows_that_are_new_intervals"] = sum(
            1 for c in candidates
            if getattr(c, "window_kind", "") == "PATH_WINDOW_G1"
            and (c.layer_to, candidate_path_offsets(models, c)) not in line_keys)
    views = {i: RouteView.prepare(r) for i, r in planar.items()}
    current_length = planar[moved].total_length()
    old_neighbors = {other}
    basic_pass = []
    basic_rejected = 0
    for candidate in candidates[:BASIC_CAP]:
        evaluation = evaluate_elevation(candidate, planar[moved], planar[other], cfg)
        if evaluation["status"] == "ACCEPTED_TARGET_PAIR_ONLY":
            basic_pass.append(candidate)
        else:
            basic_rejected += 1
    report["basic_evaluations"] = min(len(candidates), BASIC_CAP)
    report["basic_rejected"] = basic_rejected
    report["basic_passed"] = len(basic_pass)
    full_checks = 0; full_passed = 0
    for candidate in basic_pass[:FULL_CAP]:
        row, _after = full_acceptance(candidate, moved, planar[moved], current_length, views,
                                      old_neighbors, cfg)
        full_checks += 1
        if row["status"] == "ACCEPTED_FULL":
            full_passed += 1
            report.setdefault("first_accepted_geometry", dict(
                window_kind=getattr(candidate, "window_kind", "LINE_WINDOW_G0"),
                rise_window=list(candidate.rise_window), fall_window=list(candidate.fall_window),
                layer_to=candidate.layer_to, extra_length_mm=candidate.extra_length_mm,
                net_collision_reduction=row["net_collision_reduction"]))
            break
    report["full_checks"] = full_checks
    report["full_passed"] = full_passed
    report["full_check_capped"] = len(basic_pass) > FULL_CAP
    if full_passed:
        outcome = "FULL_ACCEPTED_CANDIDATE_EXISTS"
    elif not basic_pass:
        outcome = "CANDIDATES_EXIST_BASIC_ALL_REJECTED"
    elif report["full_check_capped"] and full_checks == FULL_CAP:
        outcome = "BASIC_PASSES_FULL_CHECK_CAPPED"
    else:
        outcome = "BASIC_PASSES_FULL_NO_NET_GAIN"
    report["outcome"] = outcome
    report["status"] = outcome
    return report, dict(basic=report["basic_evaluations"], full=full_checks,
                        seconds=time.perf_counter() - started)


def prefix_composition(planar, crossings, record, domain, spec, degrees):
    """Which GENERATION KIND occupies the frozen K16 prefix on this side.

    Uses the engine's own ordering and prefix helpers on the frozen planar
    state, with the same degrees map for both domains, so the only difference is
    the candidate pool. This isolates 'the generation domain grew' from
    'candidates compete for the same prefix'."""
    from src.overnight_engine_3d import order_pool, _select_k_prefix
    target = tuple(record["target_pair"])
    moved = record["moved_route_id"]
    other = record["other_route_id"]
    cfg = config()
    points = list(crossings.get(target, []))
    stats = {}
    try:
        candidates, _failures = candidate_families(planar[moved], target, points, cfg,
                                                   window_slack_mm=REG.WINDOW_SLACK_MM,
                                                   generation_domain=domain, stats_out=stats)
    except ValueError:
        return dict(domain=domain, pool=0, prefix=0, prefix_by_kind={}, pool_by_kind={})
    pool = [dict(victim_id=moved, candidate_index=i, candidate=c, other=other,
                 action="FIRST_ELEVATION",
                 window_kind=getattr(c, "window_kind", "LINE_WINDOW_G0"))
            for i, c in enumerate(candidates)]
    if not pool:
        return dict(domain=domain, pool=0, prefix=0, prefix_by_kind={}, pool_by_kind={})
    ordered = order_pool(pool, spec, degrees)
    prefix = _select_k_prefix(ordered, spec, [moved], set(), {})
    def counts(rows):
        out = Counter(row.get("window_kind", "LINE_WINDOW_G0") for row in rows)
        return {k: v for k, v in sorted(out.items())}
    return dict(domain=domain, pool=len(pool), prefix=len(prefix),
                pool_by_kind=counts(pool), prefix_by_kind=counts(prefix))


def main():
    targets = json.loads((AUDIT / "target_list.json").read_text(encoding="utf-8"))
    audit = json.loads((AUDIT / "side_audit.json").read_text(encoding="utf-8"))["records"]
    planar, crossings = load_planar_and_crossings()
    frozen_old = {tuple(sorted((r["target_pair"][0], r["target_pair"][1]))): r["outcome"]
                  for r in audit}
    print("sides", len(audit), "targets", len(targets["targets"]), flush=True)
    rows = []
    ledger = dict(basic_evaluations=0, full_neighbor_checks=0, seconds=0.,
                  excluded_from_optimisation_budgets=True,
                  basic_cap_per_side=BASIC_CAP, full_cap_per_side=FULL_CAP,
                  note=("generation + basic + capped full checks only, on the FROZEN PLANAR state; "
                        "these evaluations are booked separately and are NOT part of any appended "
                        "candidate budget"))
    started = time.perf_counter()
    partial = OUT / "diagnostics" / "v8_side_diagnostics.partial.json"
    if partial.is_file() and "--restart" not in sys.argv:
        rows = json.loads(partial.read_text(encoding="utf-8"))["rows"]
        print("resuming from", len(rows), "completed sides", flush=True)
    for index, record in enumerate(audit):
        if index < len(rows):
            continue
        row = dict(index=index, target_pair=record["target_pair"],
                   moved_route_id=record["moved_route_id"], other_route_id=record["other_route_id"],
                   category=record.get("category"), already_elevated=record.get("already_elevated"),
                   current_conflict_degree=record.get("current_conflict_degree"),
                   v4_outcome=record.get("outcome"),
                   v4_generated_candidates=record.get("generated_candidates"))
        from src.overnight_engine_3d import StrategySpec
        prefix_spec = StrategySpec("DIAG_PREFIX", target_policy="LEGACY",
                                   evaluation_policy="E2_ORDERED_K16", k_per_target=16,
                                   max_targets=200, window_slack_mm=REG.WINDOW_SLACK_MM)
        degrees = {moved_id: record.get("current_conflict_degree") or 0
                   for moved_id in (record["moved_route_id"], record["other_route_id"])}
        for domain in ("LINE_ONLY", "PATH_WINDOWS"):
            report, cost = side_report(planar, crossings, record, domain)
            report["k16_prefix"] = prefix_composition(planar, crossings, record, domain,
                                                      prefix_spec, degrees)
            ledger["basic_evaluations"] += cost["basic"]
            ledger["full_neighbor_checks"] += cost["full"]
            row["G0" if domain == "LINE_ONLY" else "G1"] = report
        rows.append(row)
        if len(rows) % 5 == 0 or len(rows) == len(audit):
            (out_dir := (OUT / "diagnostics")).mkdir(parents=True, exist_ok=True)
            (out_dir / "v8_side_diagnostics.partial.json").write_text(
                json.dumps(dict(rows=rows, completed=len(rows)), indent=2), encoding="utf-8")
        g0 = row["G0"]; g1 = row["G1"]
        print(("[%3d/%3d] %s side=%d G0=%s(%d) G1=%s(%d)" % (
            index + 1, len(audit), row["target_pair"], row["moved_route_id"],
            g0["outcome"], g0["generated_candidates"], g1["outcome"],
            g1["generated_candidates"])), flush=True)
    ledger["seconds"] = time.perf_counter() - started
    old_no_window = [r for r in rows if r["v4_outcome"] == "NO_LEGAL_WINDOW_UNDER_CURRENT_RULES"]
    summary = dict(
        frozen_diagnostic_set=dict(source=str(AUDIT), seed=targets.get("seed"),
                                   targets=len(targets["targets"]), sides=len(audit)),
        v4_outcome_counts=dict(Counter(r["v4_outcome"] for r in rows)),
        g0_outcome_counts=dict(Counter(r["G0"]["outcome"] for r in rows)),
        g1_outcome_counts=dict(Counter(r["G1"]["outcome"] for r in rows)),
        old_no_window_sides=len(old_no_window),
        old_no_window_now_g0_candidates=sum(1 for r in old_no_window
                                            if r["G0"]["generated_candidates"] > 0),
        old_no_window_now_g1_candidates=sum(1 for r in old_no_window
                                            if r["G1"]["generated_candidates"] > 0),
        old_no_window_g1_basic_passed=sum(1 for r in old_no_window if r["G1"]["basic_passed"] > 0),
        old_no_window_g1_full_passed=sum(1 for r in old_no_window if r["G1"]["full_passed"] > 0),
        old_no_window_g1_still_no_window=sum(
            1 for r in old_no_window
            if r["G1"]["outcome"] == "NO_LEGAL_WINDOW_UNDER_CURRENT_RULES"),
        old_no_window_g1_curvature_rejected_only=sum(
            1 for r in old_no_window
            if r["G1"]["outcome"] == "NO_LEGAL_WINDOW_UNDER_CURRENT_RULES"
            and r["G1"]["curvature_rejected"] > 0),
        old_no_window_g1_undecided=sum(
            1 for r in old_no_window if r["G1"]["outcome"] in (
                "BASIC_PASSES_FULL_CHECK_CAPPED", "BASIC_PASSES_FULL_NO_NET_GAIN")),
        g1_extra_candidates_total=sum(r["G1"]["generated_path_windows"] for r in rows),
        k16_prefix_by_kind={
            "G0": dict(Counter(k for r in rows for k, v in
                               (r["G0"].get("k16_prefix") or {}).get("prefix_by_kind", {}).items()
                               for _ in range(v))),
            "G1": dict(Counter(k for r in rows for k, v in
                               (r["G1"].get("k16_prefix") or {}).get("prefix_by_kind", {}).items()
                               for _ in range(v)))},
        k16_prefix_size={"G0": sum(sum((r["G0"].get("k16_prefix") or {}).get("prefix_by_kind",
                                                                           {}).values())
                                   for r in rows),
                         "G1": sum(sum((r["G1"].get("k16_prefix") or {}).get("prefix_by_kind",
                                                                            {}).values())
                                   for r in rows)},
        sides_where_path_windows_enter_the_prefix=sum(
            1 for r in rows
            if ((r["G1"].get("k16_prefix") or {}).get("prefix_by_kind", {})
                or {}).get("PATH_WINDOW_G1", 0) > 0),
        sides_where_g1_prefix_is_all_path_windows=sum(
            1 for r in rows
            if ((r["G1"].get("k16_prefix") or {}).get("prefix_by_kind", {})
                or {}).get("PATH_WINDOW_G1", 0) > 0
            and ((r["G1"].get("k16_prefix") or {}).get("prefix_by_kind", {})
                 or {}).get("LINE_WINDOW_G0", 0) == 0),
        g1_curvature_rejected_total=sum(r["G1"]["curvature_rejected"] for r in rows),
        g1_dedup_removed_total=sum(
            (r["G1"]["generation_stats"] or {}).get("path_window_dedup_removed", 0) for r in rows),
        ledger=ledger,
        wording=("a side with zero candidates has no legal window under the evaluated generation "
                 "rules; it is never 'geometrically infeasible'"))
    out_dir = OUT / "diagnostics"; out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "v8_side_diagnostics.json").write_text(
        json.dumps(dict(summary=summary, rows=rows), indent=2), encoding="utf-8")
    with (out_dir / "v8_side_diagnostics.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["side_index", "target_pair", "moved", "other", "category", "v4_outcome",
                         "g0_candidates", "g0_outcome", "g1_candidates", "g1_path_windows",
                         "g1_curvature_rejected", "g1_outcome", "g1_basic_passed",
                         "g1_full_passed", "g1_new_intervals"])
        for row in rows:
            writer.writerow([row["index"], row["target_pair"], row["moved_route_id"],
                             row["other_route_id"], row["category"], row["v4_outcome"],
                             row["G0"]["generated_candidates"], row["G0"]["outcome"],
                             row["G1"]["generated_candidates"],
                             row["G1"]["generated_path_windows"], row["G1"]["curvature_rejected"],
                             row["G1"]["outcome"], row["G1"]["basic_passed"],
                             row["G1"]["full_passed"],
                             row["G1"].get("path_windows_that_are_new_intervals")])
    (out_dir / "v8_side_diagnostics_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2)[:4000], flush=True)


if __name__ == "__main__":
    main()
