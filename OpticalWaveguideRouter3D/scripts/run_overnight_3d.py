"""Generic overnight driver: run one pre-registered group of one round.

Usage (project root):
    .venv\\Scripts\\python.exe -B scripts\\run_overnight_3d.py PROJECT OUTDIR \\
        --round v5 --group V5_STRATIFIED_N720 [--group ...] [--freeze]

A group can only run when it is present in the frozen manifest written by
scripts/freeze_overnight_manifest.py, so no configuration can be invented after
seeing a result. Every group independently rescans all 130,816 pairs of its own
start state and, at the end, saves, reloads and rescans the terminal state and
checks the near-distance sets, geometry and all three length measures.
"""
import sys, json, hashlib, platform, traceback, argparse
from collections import Counter
from copy import deepcopy
from pathlib import Path
from itertools import combinations
from time import perf_counter


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_args(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("project"); ap.add_argument("outdir")
    ap.add_argument("--round", required=True)
    ap.add_argument("--group", action="append", default=[])
    ap.add_argument("--adoption", default=None)
    ap.add_argument("--tag", default="")
    return ap.parse_args(argv[1:])


ARGS = parse_args(sys.argv)
ROOT = Path(ARGS.project).resolve(); OUT = Path(ARGS.outdir).resolve()
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))

from src.models import Layer, Point3D
from src.geometry_3d import (lift_smoothed_route_to_layer, CosineTransition3D,
    PathWindowTransition3D, TRANSITION_TYPES)
from src.geometry_3d_diagnostics import analyze_route3d_joins
from src.multi_attribution import deserialize_plot
from src.sequential_elevation_3d import RouteView, pair_status
from src.three_layer_assignment_3d import LayerConfiguration
from src.fixed_1024_routing import serialize_route3d, deserialize_route3d
from src.strategy_v2_3d import xy_projection_preserved, route_layer
from src.overnight_engine_3d import run_strategy, pair_state_distribution, elevation_structure
import overnight_registry as REG

SIZE = REG.SIZE


def three_layer_config():
    return LayerConfiguration([Layer(0, 0.), Layer(1, 1.), Layer(2, 2.)], REG.CLEARANCE_MM,
                              REG.REQUIRED_RADIUS_MM, "LINE_ONLY_FINITE_WINDOWS",
                              "EXPERIMENTAL_SYNTHETIC")


def config_record(config):
    return dict(layers=[dict(id=l.id, z=l.z) for l in config.layers],
                clearance_mm=config.clearance_mm, required_radius_mm=config.required_radius_mm,
                transition_policy=config.transition_policy,
                parameter_status=config.parameter_status)


def environment_record():
    return dict(python=sys.version.split()[0], implementation=platform.python_implementation(),
                platform=platform.platform(), executable=sys.executable)


def code_version():
    files = sorted((ROOT / "src").glob("*.py")) + [Path(__file__).resolve(),
                                                   ROOT / "scripts/overnight_registry.py"]
    return dict(recorded_hashes={str(p.relative_to(ROOT)): sha256(p) for p in files if p.is_file()},
                note="overnight engine; hashes cover every src/*.py module, this driver and the registry")


def load_planar_and_crossings():
    plotpath = ROOT / "outputs/step_8_5_legacy_512_plot_geometry.json"
    eventpath = ROOT / "outputs/step_8_5_legacy_512_physical_events.jsonl"
    planar = {r["id"]: lift_smoothed_route_to_layer(deserialize_plot(r), Layer(0, 0))
              for r in json.loads(plotpath.read_text())["routes"]}
    crossings = {}
    for text in eventpath.read_text().splitlines():
        e = json.loads(text)
        if e["kind"] == "cross":
            crossings.setdefault(tuple(sorted((e["route_a_id"], e["route_b_id"]))), []).append(
                Point3D(e["point"]["x"], e["point"]["y"], 0))
    return planar, crossings, {str(plotpath): sha256(plotpath), str(eventpath): sha256(eventpath)}


def load_start(kind):
    directory = ROOT / (REG.MAIN_START if kind == "main" else REG.CHALLENGE_START)
    routes = {row["route_id"]: deserialize_route3d(row["geometry"])
              for row in json.loads((directory / "final_routes.json").read_text(encoding="utf-8"))["routes"]}
    sets = json.loads((directory / "collision_sets.json").read_text(encoding="utf-8"))
    return directory, routes, sets


def full_scan(routes, log_prefix="  scan"):
    started = perf_counter(); checks = 0
    views = {i: RouteView.prepare(r) for i, r in routes.items()}
    pairs = set(); unknown = set()
    for a, b in combinations(sorted(routes), 2):
        status = pair_status(views[a], views[b], REG.CLEARANCE_MM); checks += 1
        if status == "COLLISION":
            pairs.add((a, b))
        elif status != "CLEAR":
            unknown.add((a, b))
    assert checks == len(routes) * (len(routes) - 1) // 2
    return dict(checks=checks, pairs=pairs, unknown=unknown, seconds=perf_counter() - started)


def geometry_audit(planar, routes):
    endpoints_ok = joins_ok = radius_ok = xy_ok = structure_ok = True; failures = []
    for i, r in routes.items():
        if r.start_point != planar[i].start_point or r.end_point != planar[i].end_point:
            endpoints_ok = False
        joins = analyze_route3d_joins(r)
        if not (joins.all_C0 and joins.all_C1_direction): joins_ok = False
        transitions = [p for p in r.primitives if isinstance(p, TRANSITION_TYPES)]
        for p in transitions:
            if p.minimum_curvature_radius() < REG.REQUIRED_RADIUS_MM: radius_ok = False
        ok, reason = xy_projection_preserved(r, planar[i])
        if not ok: xy_ok = False; failures.append((i, reason))
        structure, structure_reason = elevation_structure(r)
        if not structure: structure_ok = False; failures.append((i, structure_reason))
    return dict(endpoint_invariant=endpoints_ok, joins_C0_C1_direction=joins_ok,
                transition_radius_pass=radius_ok, xy_projection_preserved=xy_ok,
                single_elevation_structure=structure_ok, failures=failures[:10])


def saved_state_audit(state_path, sets_path, planar, planar_total_length, start_total_length):
    stored = {row["route_id"]: deserialize_route3d(row["geometry"])
              for row in json.loads(state_path.read_text(encoding="utf-8"))["routes"]}
    geometry = geometry_audit(planar, stored)
    recheck = full_scan(stored, log_prefix="  recheck")
    sets = json.loads(sets_path.read_text(encoding="utf-8"))
    pairs = set(map(tuple, sets["final_collision_pairs"]))
    unknown = set(map(tuple, sets["final_unresolved_pairs"]))
    final_total = sum(r.total_length() for r in stored.values())
    moved = {i for i, r in stored.items() if any(isinstance(p, TRANSITION_TYPES) for p in r.primitives)}
    record = dict(reloaded_route_count=len(stored),
                  collision_pair_set_matches_incremental=recheck["pairs"] == pairs,
                  unresolved_pair_set_matches_incremental=recheck["unknown"] == unknown,
                  geometry=geometry, checks=recheck["checks"], recheck_seconds=recheck["seconds"],
                  final_transition_count=sum(isinstance(p, TRANSITION_TYPES)
                                             for r in stored.values() for p in r.primitives),
                  final_path_window_count=sum(type(p) is PathWindowTransition3D
                                              for r in stored.values() for p in r.primitives),
                  minimum_path_window_radius_mm=min(
                      (p.minimum_curvature_radius() for r in stored.values()
                       for p in r.primitives if type(p) is PathWindowTransition3D),
                      default=None),
                  elevated_route_count=len(moved),
                  layer_route_counts={str(k): v for k, v in sorted(Counter(route_layer(r)
                                                                     for r in stored.values()).items())},
                  length_ledger=dict(
                      saved_final_total_length_mm=final_total,
                      recorded_final_total_length_mm=sets["ledger_final_total_length_mm"],
                      total_length_matches=abs(final_total - sets["ledger_final_total_length_mm"]) < 1e-9,
                      stage_length_delta_mm=final_total - start_total_length,
                      stage_length_delta_matches=abs((final_total - start_total_length)
                                                     - sets["ledger_stage_length_delta_mm"]) < 1e-6,
                      step_length_delta_sum_mm=sets["ledger_step_length_delta_mm"],
                      step_delta_sum_matches_stage=abs(sets["ledger_step_length_delta_mm"]
                                                       - (final_total - start_total_length)) < 1e-6,
                      final_extra_length_vs_planar_mm=final_total - planar_total_length,
                      recorded_final_extra_length_vs_planar_mm=sets["ledger_final_extra_length_vs_planar_mm"],
                      final_extra_length_matches=abs((final_total - planar_total_length)
                                                     - sets["ledger_final_extra_length_vs_planar_mm"]) < 1e-6),
                  final_pair_state_distribution=pair_state_distribution(pairs, moved))
    ok = (record["reloaded_route_count"] == SIZE
          and record["collision_pair_set_matches_incremental"]
          and record["unresolved_pair_set_matches_incremental"]
          and geometry["endpoint_invariant"] and geometry["joins_C0_C1_direction"]
          and geometry["transition_radius_pass"] and geometry["xy_projection_preserved"]
          and geometry["single_elevation_structure"]
          and record["length_ledger"]["total_length_matches"]
          and record["length_ledger"]["stage_length_delta_matches"]
          and record["length_ledger"]["step_delta_sum_matches_stage"]
          and record["length_ledger"]["final_extra_length_matches"])
    record["verdict"] = "PASS" if ok else "FAIL"
    return record


def save(folder, name, data, compact=False):
    def encode(x):
        if isinstance(x, tuple): return list(x)
        if type(x).__name__ == "Layer": return dict(id=x.id, z=x.z)
        raise TypeError(type(x).__name__)
    text = (json.dumps(data, default=encode, separators=(",", ":"), allow_nan=False) if compact
            else json.dumps(data, default=encode, indent=2, allow_nan=False))
    (folder / name).write_text(text, encoding="utf-8")


def main():
    adoption = {}
    if ARGS.adoption:
        adoption = json.loads(Path(ARGS.adoption).read_text(encoding="utf-8"))
    index = REG.group_index(ARGS.round, adoption)
    wanted = ARGS.group or sorted(index)
    unknown = [g for g in wanted if g not in index]
    if unknown: raise SystemExit("group not in round " + ARGS.round + ": " + str(unknown))
    manifest_path = OUT / "manifest" / ("round_" + ARGS.round + ".json")
    if not manifest_path.is_file():
        raise SystemExit("frozen manifest missing: " + str(manifest_path)
                         + "; run scripts/freeze_overnight_manifest.py first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frozen_groups = set(manifest["groups"])
    missing = [g for g in wanted if g not in frozen_groups]
    if missing: raise SystemExit("group not pre-registered in the frozen manifest: " + str(missing))
    planar, crossings, fingerprints = load_planar_and_crossings()
    planar_total_length = sum(r.total_length() for r in planar.values())
    starts = {}
    for kind in {index[g]["start"] for g in wanted}:
        directory, routes, sets = load_start(kind)
        print("start-state rescan (" + kind + ") ...", flush=True)
        scan = full_scan(routes, log_prefix="  " + kind)
        start_unknown = set(map(tuple, sets["final_unresolved_pairs"]))
        saved_pairs = set(map(tuple, sets["final_collision_pairs"]))
        moved = {i for i, r in routes.items() if any(isinstance(p, CosineTransition3D)
                                                     for p in r.primitives)}
        state = dict(start_kind=kind, directory=str(directory), route_count=len(routes),
                     checks=scan["checks"], recomputed_collision_pair_count=len(scan["pairs"]),
                     saved_collision_pair_count=len(saved_pairs),
                     recomputed_pair_set_matches_saved=scan["pairs"] == saved_pairs,
                     recomputed_unresolved_pair_count=len(scan["unknown"]),
                     saved_unresolved_pair_count=len(start_unknown),
                     recomputed_unresolved_set_matches_saved=scan["unknown"] == start_unknown,
                     elevated_route_count=len(moved),
                     pair_state_distribution=pair_state_distribution(scan["pairs"], moved),
                     start_total_length_mm=sum(r.total_length() for r in routes.values()),
                     planar_total_length_mm=planar_total_length, scan_seconds=scan["seconds"])
        state["verdict"] = "PASS" if (state["recomputed_pair_set_matches_saved"]
                                      and state["recomputed_unresolved_set_matches_saved"]) else "FAIL"
        (OUT / ("start_check_" + kind + ".json")).write_text(json.dumps(state, indent=2), encoding="utf-8")
        print("  " + kind + " " + state["verdict"] + " pairs=" + str(len(scan["pairs"]))
              + " unresolved=" + str(len(scan["unknown"])) + " elevated=" + str(len(moved)), flush=True)
        if state["verdict"] != "PASS": raise SystemExit("START_STATE_CHECK_FAILED:" + kind)
        starts[kind] = (directory, routes, scan, start_unknown)

    config = three_layer_config()
    for name in wanted:
        group = index[name]; spec = group["spec"]; mode = group["mode"]; budget = group["budget"]
        kind = group["start"]
        directory, start_routes, scan, start_unknown = starts[kind]
        folder_name = name + (("_" + ARGS.tag) if ARGS.tag else "")
        folder = OUT / ARGS.round / folder_name; folder.mkdir(parents=True, exist_ok=True)
        logfile = (folder / ("run_" + folder_name + ".log")).open("a", encoding="utf-8")
        started = perf_counter()
        def log(message, _f=logfile, _n=folder_name):
            text = "[" + str(round(perf_counter(), 1)) + "] " + _n + ": " + message
            print(text, flush=True); _f.write(text + "\n"); _f.flush()
        log("start mode=" + mode + " budget=" + str(budget) + " spec=" + json.dumps(spec.as_dict()))
        log("start state=" + kind + " " + str(directory) + " pairs=" + str(len(scan["pairs"])))
        save(folder, "config.json", dict(scale=SIZE,
             dataset="LEGACY_512_SMOOTHED_P0", input_files=["outputs/step_8_5_legacy_512_plot_geometry.json",
             "outputs/step_8_5_legacy_512_physical_events.jsonl"], input_sha256=fingerprints,
             start_state_directory=str(directory), start_kind=kind,
             start_state_sha256={f: sha256(directory / f) for f in
                                 ("final_routes.json", "collision_sets.json", "ledger.json",
                                  "decisions.json", "summary.json") if (directory / f).is_file()},
             configuration=config_record(config), strategy=spec.name, strategy_spec=spec.as_dict(),
             mode=mode, allow_relocation=(mode == "R"), appended_candidate_budget=budget,
             max_targets=spec.max_targets, candidate_budget_scope=("appended to the start state; the "
                 "historical evaluations that produced it are excluded"),
             generation_failure_cache=True, round=ARGS.round, group=name, control=group["control"],
             adoption=adoption, adoption_rule=REG.ADOPTION_RULE,
             manifest_sha256=sha256(manifest_path), tag=ARGS.tag))
        save(folder, "code_version.json", code_version())
        save(folder, "environment.json", environment_record())
        start_total_length = sum(r.total_length() for r in start_routes.values())
        initial_routes = {i: deepcopy(r) for i, r in start_routes.items()}

        def progress(row):
            if row.get("phase") == "TARGET_DONE":
                log("step " + str(row["step"]) + " " + str(row["status"]) + " pairs="
                    + str(row["collisions"]) + " evals=" + str(row["candidate_evaluations"])
                    + " " + str(int(row["seconds"])) + "s")
            elif row.get("phase") == "INITIAL_DONE":
                log("INITIAL_DONE pairs=" + str(row["collisions"]))

        result = run_strategy(initial_routes, planar, config, mode=mode,
                              appended_candidate_budget=budget, spec=spec,
                              saved_crossings=crossings, initial_pairs=scan["pairs"],
                              initial_uncertain=start_unknown, generation_failure_cache=True,
                              progress=progress)
        ledger = result["ledger"]
        log("done final=" + str(ledger["final_collision_pair_count"]) + " moves="
            + str(ledger["accepted_moves"]) + " first=" + str(ledger["first_elevations"])
            + " reloc=" + str(ledger["relocations"]) + " ret=" + str(ledger["returns"])
            + " evals=" + str(ledger["candidate_evaluations"]) + " stop=" + str(ledger["stop_reason"]))
        save(folder, "decisions.json", result["steps"], compact=True)
        save(folder, "generation_skips.json", result["generation_skips"])
        save(folder, "route_skips.json", result["route_skips"])
        save(folder, "curve.json", result["curve"])
        save(folder, "final_routes.json", dict(route_count=SIZE,
             routes=[dict(route_id=i, main_layer=route_layer(r), geometry=serialize_route3d(r))
                     for i, r in sorted(result["routes"].items())]))
        save(folder, "collision_sets.json", dict(
            initial_collision_pairs=result["initial_collision_pairs"],
            final_collision_pairs=result["final_collision_pairs"],
            initial_unresolved_pairs=result["initial_unresolved_pairs"],
            final_unresolved_pairs=result["final_unresolved_pairs"],
            elevated_route_ids=result["elevated_route_ids"],
            relocated_route_ids=result["relocated_route_ids"],
            returned_route_ids=result["returned_route_ids"],
            ledger_step_length_delta_mm=ledger["total_step_length_delta_mm"],
            ledger_stage_length_delta_mm=ledger["stage_length_delta_mm"],
            ledger_final_total_length_mm=ledger["final_total_length_mm"],
            ledger_final_extra_length_vs_planar_mm=ledger["final_extra_length_vs_planar_mm"]),
            compact=True)
        save(folder, "ledger.json", ledger)
        recheck = saved_state_audit(folder / "final_routes.json", folder / "collision_sets.json",
                                    planar, planar_total_length, start_total_length)
        (folder / "recheck.json").write_text(json.dumps(recheck, indent=2), encoding="utf-8")
        log("recheck " + recheck["verdict"] + " checks=" + str(recheck["checks"]))
        stats = dict(group=name, strategy=spec.name, strategy_spec=spec.as_dict(), mode=mode,
                     appended_candidate_budget=budget, max_targets=spec.max_targets, start_kind=kind,
                     control=group["control"],
                     initial_collision_pairs=ledger["initial_collision_pair_count"],
                     final_collision_pairs=ledger["final_collision_pair_count"],
                     final_unresolved_pairs=ledger["final_unresolved_pair_count"],
                     net_collision_reduction=ledger["net_collision_reduction"],
                     accepted_moves=ledger["accepted_moves"], first_elevations=ledger["first_elevations"],
                     relocations=ledger["relocations"], returns=ledger["returns"],
                     first_elevation_net_reduction=ledger["first_elevation_net_reduction"],
                     relocation_net_reduction=ledger["relocation_net_reduction"],
                     return_net_reduction=ledger["return_net_reduction"],
                     total_old_collisions_removed=ledger["total_old_collisions_removed"],
                     total_new_collisions_created=ledger["total_new_collisions_created"],
                     generated_candidates=ledger["generated_candidates"],
                     candidate_evaluations=ledger["candidate_evaluations"],
                     full_neighbor_checks=ledger["full_neighbor_checks"],
                     full_acceptance_passes=ledger["full_acceptance_passes"],
                     executed_moves=ledger["executed_moves"], stop_reason=ledger["stop_reason"],
                     target_attempts=ledger["target_attempts"],
                     evaluations_per_action=ledger["evaluations_per_action"],
                     net_reduction_per_evaluation=ledger["net_reduction_per_evaluation"],
                     relocation_candidate_evaluations=ledger["relocation_candidate_evaluations"],
                     not_evaluated_candidates=ledger["not_evaluated_candidates"],
                     deferred_prefix_no_winner=ledger["deferred_prefix_no_winner"],
                     dedup_removed_duplicates=ledger["dedup_removed_duplicates"],
                     decision_cache_hits=ledger["decision_cache_hits"],
                     coverage=ledger["coverage"],
                     stage_length_delta_mm=ledger["stage_length_delta_mm"],
                     final_extra_length_vs_planar_mm=ledger["final_extra_length_vs_planar_mm"],
                     start_extra_length_vs_planar_mm=ledger["start_extra_length_vs_planar_mm"],
                     final_transition_count=ledger["final_transition_count"],
                     final_elevated_route_count=ledger["final_elevated_route_count"],
                     layer_route_counts=ledger["layer_route_counts"],
                     basic_rejection_reason_counts=ledger["basic_rejection_reason_counts"],
                     full_rejection_reason_counts=ledger["full_rejection_reason_counts"],
                     generation_failure_reason_counts=ledger["generation_failure_reason_counts"],
                     budget_checkpoints=ledger["budget_checkpoints"],
                     timings=dict(initial_pair_scan_seconds=ledger["initial_pair_scan_seconds"],
                                  assignment_seconds=ledger["assignment_seconds"],
                                  runtime_seconds=ledger["runtime_seconds"],
                                  run_seconds_including_recheck=perf_counter() - started),
                     recheck={k: v for k, v in recheck.items() if k != "geometry"},
                     recheck_geometry=recheck["geometry"],
                     recheck_length_ledger=recheck["length_ledger"])
        save(folder, "summary.json", dict(scale=SIZE, round=ARGS.round, group=name,
                                          strategy=spec.name, stats=stats))
        logfile.close()
        print("GROUP DONE " + name + " " + recheck["verdict"], flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("FAILED\n" + traceback.format_exc(), flush=True)
        raise
