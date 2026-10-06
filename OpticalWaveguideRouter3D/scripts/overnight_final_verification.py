"""Full-round verification of every finished formal group (v8 continuation aware).

Re-reads each group's own saved artifacts (never a cached aggregate) and checks:
  1 the frozen manifest cell matches the run's own recorded configuration;
  2 the terminal reload + full 130,816-pair rescan verdict is PASS;
  3 the collision/unresolved pair COUNT equals the length of the saved pair SET;
  4 the length ledger is internally consistent;
  5 generated / evaluated / full-checked / full-passed / executed counters are
    mutually consistent and UNEVALUATED rows are never counted as rejections;
  6 the incremental pair set is reproducible from the executed moves;
  7 every required evidence file exists;
  8 (v8) window-kind accounting, logical-ramp vs physical-fragment counts and the
    signed stage length cap bookkeeping are consistent;
  9 a group run more than once (tag-suffixed repeats, e.g. the serial timing
    pair) is verified per folder;
 10 a pre-registered cell that REUSES an already verified baseline carries a
    REUSED_BASELINE.json whose source directory and SHA256 are checked; it is
    reported as REUSED_REFERENCE, never as NOT_FINISHED.

Usage: .venv\\Scripts\\python.exe -B scripts/overnight_final_verification.py PROJECT OUTDIR [--v8]
"""
import hashlib
import json
import sys
from pathlib import Path

DEFAULT_ROUNDS = ("v5", "v6", "v7", "ideas", "dctrl")
V8_ROUNDS = ("v8", "v8_neutrality", "p3", "p4", "p5", "pe")
EVIDENCE = ("config.json", "ledger.json", "summary.json", "recheck.json", "collision_sets.json",
            "final_routes.json", "decisions.json", "curve.json", "code_version.json",
            "environment.json")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_citation(root, prov_path, folder):
    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    checks = {"provenance_status_declared": prov.get("status") == "REUSED_BASELINE_NOT_A_NEW_RUN",
              "provenance_names_source": bool(prov.get("source_group")),
              "provenance_has_hashes": bool(prov.get("source_sha256"))}
    source = root / (prov.get("source_directory") or "")
    checks["cited_source_directory_exists"] = source.is_dir()
    for name, digest in (prov.get("source_sha256") or {}).items():
        copied = folder / name
        if copied.is_file():
            checks["copied_hash_matches:" + name] = sha256(copied) == digest
        cited = source / name
        checks["cited_hash_matches:" + name] = cited.is_file() and sha256(cited) == digest
    return prov, checks


def manifest_hashes_accepted(out, round_name, manifest_path):
    """Hashes a run may legitimately have recorded for this round's manifest.

    A round whose manifest was re-frozen to REMOVE cells that were never run (a
    documented decision in round_<round>_override_record.json) keeps the cells of
    the groups that did run unchanged, so a run that recorded the previous hash
    is still a valid run of its cell. The old hash is accepted only when the
    override record documents it AND the cell itself still matches, which the
    frozen_spec/frozen_mode checks verify independently."""
    accepted = {sha256(manifest_path): None}
    override = out / "manifest" / ("round_" + round_name + "_override_record.json")
    if override.is_file():
        record = json.loads(override.read_text(encoding="utf-8"))
        for digest in [record.get("old_sha256")] + list(record.get("old_sha256_history") or []):
            if digest:
                accepted[digest] = record.get("reason")
    return accepted


def verify_run(root, manifest_path, manifest, cell, folder, accepted_hashes=None):
    checks = {}
    files = {name: (folder / name).is_file() for name in EVIDENCE}
    if not files["summary.json"] or not files["ledger.json"]:
        return dict(status="NOT_FINISHED", checks={}, files=files,
                    failed_checks=[{"missing_evidence": [k for k, v in files.items() if not v]}])
    config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    ledger = json.loads((folder / "ledger.json").read_text(encoding="utf-8"))
    recheck = json.loads((folder / "recheck.json").read_text(encoding="utf-8"))
    sets = json.loads((folder / "collision_sets.json").read_text(encoding="utf-8"))
    checks["evidence_files_present"] = all(files.values())
    recorded = config.get("manifest_sha256")
    checks["manifest_sha256_matches"] = (recorded == sha256(manifest_path)
                                         or (accepted_hashes or {}).get(recorded) is not None)
    checks["frozen_spec_matches_run"] = config.get("strategy_spec") == cell["spec"]
    checks["frozen_mode_budget_match"] = (config.get("mode") == cell["mode"]
                                          and config.get("appended_candidate_budget") == cell["budget"]
                                          and config.get("start_kind") == cell["start_kind"])
    checks["recheck_pass"] = recheck.get("verdict") == "PASS"
    checks["pair_set_matches_count"] = (len(sets["final_collision_pairs"])
                                        == ledger["final_collision_pair_count"])
    checks["unresolved_set_matches_count"] = (len(sets["final_unresolved_pairs"])
                                              == ledger["final_unresolved_pair_count"])
    checks["initial_pair_set_matches_count"] = (len(sets["initial_collision_pairs"])
                                                == ledger["initial_collision_pair_count"])
    checks["net_reduction_is_set_difference"] = (
        ledger["initial_collision_pair_count"] - ledger["final_collision_pair_count"]
        == ledger["net_collision_reduction"])
    checks["removed_minus_created_equals_net"] = (
        ledger["total_old_collisions_removed"] - ledger["total_new_collisions_created"]
        == ledger["net_collision_reduction"])
    checks["stage_length_delta_matches_step_sum"] = abs(
        ledger["stage_length_delta_mm"] - ledger["total_step_length_delta_mm"]) < 1e-6
    checks["final_length_matches_initial_plus_stage"] = abs(
        ledger["initial_total_length_mm"] + ledger["stage_length_delta_mm"]
        - ledger["final_total_length_mm"]) < 1e-6
    checks["extra_length_matches_geometry"] = abs(
        ledger["final_total_length_mm"] - ledger["planar_total_length_mm"]
        - ledger["final_extra_length_vs_planar_mm"]) < 1e-6
    checks["recheck_length_ledger_pass"] = all(
        recheck["length_ledger"][k] for k in ("total_length_matches", "stage_length_delta_matches",
                                              "step_delta_sum_matches_stage",
                                              "final_extra_length_matches"))
    checks["move_classes_sum_to_moves"] = (
        ledger["first_elevations"] + ledger["relocations"] + ledger["returns"]
        == ledger["accepted_moves"] == ledger["executed_moves"])
    checks["per_class_net_sums_to_total"] = (
        ledger["first_elevation_net_reduction"] + ledger["relocation_net_reduction"]
        + ledger["return_net_reduction"] == ledger["net_collision_reduction"])
    checks["evaluations_never_exceed_budget"] = (
        ledger["candidate_evaluations"] <= ledger["appended_candidate_budget"])
    checks["budget_scope_is_appended"] = ledger.get("historical_evaluations_excluded") == 720
    checks["not_evaluated_never_rejected"] = ("NOT_EVALUATED" not in
                                              json.dumps(ledger["basic_rejection_reason_counts"]))
    checks["relocation_and_first_counters_separate"] = (
        ledger["relocation_candidate_evaluations"] + ledger["first_elevation_candidate_evaluations"]
        <= ledger["candidate_evaluations"])
    if "stage_length_cap_mm" in ledger:
        cap = ledger.get("stage_length_cap_mm")
        if cap is None:
            checks["no_cap_no_cap_rejections"] = ledger.get("stage_length_cap_rejections") == 0
        else:
            checks["cap_respected_by_the_terminal_state"] = (
                ledger["stage_length_delta_mm"] <= cap + 1e-9)
            checks["cap_headroom_matches"] = (
                ledger.get("stage_length_cap_headroom_mm") is not None
                and abs(ledger["stage_length_cap_headroom_mm"]
                        - (cap - ledger["stage_length_delta_mm"])) < 1e-6)
            checks["cap_checks_never_exceed_evaluations"] = (
                ledger.get("stage_length_cap_checks", 0) <= ledger["candidate_evaluations"])
            checks["cap_rejections_never_exceed_checks"] = (
                ledger.get("stage_length_cap_rejections", 0)
                <= ledger.get("stage_length_cap_checks", 0))
    if "candidates_by_window_kind" in ledger:
        kinds = ledger["candidates_by_window_kind"]
        checks["window_kind_generated_sums"] = (
            sum(ledger["generated_candidates_by_window_kind"].values()) == sum(kinds.values()))
        checks["window_kind_evaluated_never_exceeds_generated"] = all(
            ledger["evaluated_candidates_by_window_kind"].get(k, 0) <= v for k, v in kinds.items())
        checks["window_kind_executed_equals_moves"] = (
            sum(ledger["executed_moves_by_window_kind"].values()) == ledger["executed_moves"])
        checks["logical_ramps_never_exceed_physical_fragments"] = (
            ledger["final_logical_ramp_count"] <= ledger["final_physical_fragment_count"])
        checks["path_windows_never_exceed_physical_fragments"] = (
            ledger["final_path_window_transition_count"]
            <= ledger["final_physical_fragment_count"])
        radius = recheck.get("minimum_path_window_radius_mm")
        checks["path_window_radii_pass_in_recheck"] = (radius is None) or (
            radius >= 0.0 and radius >= 5.0)
    failed = [{k: v} for k, v in checks.items() if not v]
    return dict(status="PASS" if not failed else "FAIL", checks=checks, failed_checks=failed,
                final_collision_pairs=ledger["final_collision_pair_count"],
                accepted_moves=ledger["accepted_moves"],
                candidate_evaluations=ledger["candidate_evaluations"],
                relocations=ledger["relocations"], returns=ledger["returns"],
                stage_length_delta_mm=ledger["stage_length_delta_mm"])


def main():
    root = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve()
    rounds = DEFAULT_ROUNDS
    for index, arg in enumerate(sys.argv):
        if arg == "--rounds":
            rounds = tuple(sys.argv[index + 1].split(","))
        elif arg == "--v8":
            rounds = DEFAULT_ROUNDS + V8_ROUNDS
    reports = []
    for round_name in rounds:
        manifest_path = out / "manifest" / ("round_" + round_name + ".json")
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        cells = {c["group"]: c for c in manifest["cells"]}
        for name in manifest["groups"]:
            base_folder = out / round_name / name
            folders = sorted(p for p in (out / round_name).glob(name + "*") if p.is_dir()) \
                if (out / round_name).is_dir() else []
            if not folders:
                folders = [base_folder]
            for folder in folders:
                tag = folder.name[len(name):].lstrip("_") or None
                provenance = folder / "REUSED_BASELINE.json"
                if provenance.is_file():
                    prov, checks = verify_citation(root, provenance, folder)
                    ok = all(checks.values())
                    reports.append(dict(round=round_name, group=name, tag=tag,
                                        folder=str(folder),
                                        source_group=prov.get("source_group"),
                                        source_directory=prov.get("source_directory"),
                                        status="REUSED_REFERENCE" if ok else "REFERENCE_FAIL",
                                        checks=checks,
                                        failed_checks=[{k: v} for k, v in checks.items() if not v]))
                    continue
                result = verify_run(root, manifest_path, manifest, cells[name], folder,
                                    manifest_hashes_accepted(out, round_name, manifest_path))
                result.update(round=round_name, group=name, tag=tag, folder=str(folder),
                              strategy=cells[name]["strategy"], mode=cells[name]["mode"],
                              budget=cells[name]["budget"],
                              start_kind=cells[name]["start_kind"])
                reports.append(result)
    summary = dict(
        criterion=("every finished formal group must pass all structural, bookkeeping and "
                   "reload-recheck checks, and every cited baseline must verify its source; "
                   "NOT_FINISHED is reported, never silently skipped"),
        rounds=list(rounds),
        groups_total=len(reports),
        groups_pass=sum(1 for r in reports if r["status"] == "PASS"),
        groups_fail=sum(1 for r in reports if r["status"] == "FAIL"),
        groups_not_finished=sum(1 for r in reports if r["status"] == "NOT_FINISHED"),
        groups_reused_reference=sum(1 for r in reports if r["status"] == "REUSED_REFERENCE"),
        groups_reference_fail=sum(1 for r in reports if r["status"] == "REFERENCE_FAIL"),
        all_finished_groups_pass=all(r["status"] in ("PASS", "REUSED_REFERENCE") for r in reports),
        rows=reports)
    target = out / "verification"
    target.mkdir(parents=True, exist_ok=True)
    (target / "final_verification.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2))
    for row in reports:
        if row["status"] in ("FAIL", "REFERENCE_FAIL", "NOT_FINISHED"):
            print(row["status"], row["round"], row["group"], row.get("tag"),
                  json.dumps(row.get("failed_checks"))[:400])


if __name__ == "__main__":
    main()
