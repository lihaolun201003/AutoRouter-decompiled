"""Build the v8-continuation comparison tables from the frozen group summaries.

Reads only saved artefacts: the referenced historical rounds live in
outputs/overnight_3d_ideas/<round>/<group>/summary.json and the new rounds in
outputs/overnight_3d_continuation/<round>/<group>/summary.json. A group that is
missing is reported as MISSING, never silently dropped.

Usage:
  python -B scripts/v8_compare.py PROJECT OUTDIR [--section p2,p3,p4,p5,neutrality]
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))

HISTORICAL = ROOT / "outputs/overnight_3d_ideas"
CURRENT = OUT
SECTIONS = ("p2", "p3", "p4", "p5", "neutrality", "pe")
WANTED = None
for index, arg in enumerate(sys.argv):
    if arg == "--section":
        WANTED = tuple(sys.argv[index + 1].split(","))

FIELDS = ("final_collision_pairs", "candidate_evaluations", "accepted_moves", "first_elevations",
          "relocations", "returns", "stop_reason", "target_attempts", "net_collision_reduction",
          "stage_length_delta_mm", "final_extra_length_vs_planar_mm", "final_transition_count",
          "final_path_window_transition_count", "final_logical_ramp_count",
          "final_physical_fragment_count", "final_unresolved_pairs", "final_elevated_route_count",
          "full_neighbor_checks", "full_acceptance_passes", "not_evaluated_candidates",
          "generated_candidates", "max_targets", "appended_candidate_budget",
          "stage_length_cap_mm", "stage_length_cap_rejections", "stage_length_cap_checks",
          "stage_length_cap_headroom_mm", "decision_cache_hits",
          "relocation_candidate_evaluations", "evaluations_per_action",
          "net_reduction_per_evaluation")


TAG_SUFFIXES = ("_boundaryfix", "_refreeze", "")


def summary_path(round_name, group):
    """Prefer a fixed re-run (tag-suffixed folder) over the original folder."""
    for suffix in TAG_SUFFIXES:
        for base in (CURRENT, HISTORICAL):
            path = base / round_name / (group + suffix) / "summary.json"
            if path.is_file():
                return path, base
    return None, None


def group_folder(round_name, group):
    """Folder actually used for a group, honouring the fixed-re-run tags."""
    for suffix in TAG_SUFFIXES:
        for base in (CURRENT, HISTORICAL):
            folder = base / round_name / (group + suffix)
            if (folder / "summary.json").is_file():
                return folder, base
    return None, None


def load(round_name, group):
    path, base = summary_path(round_name, group)
    if path is None:
        return dict(group=group, round=round_name, status="MISSING")
    document = json.loads(path.read_text(encoding="utf-8"))
    stats = document["stats"]
    row = dict(group=group, round=round_name, status="PRESENT", source=str(path),
               source_root=("continuation" if base is CURRENT else "overnight_3d_ideas"))
    for field in FIELDS:
        row[field] = stats.get(field)
    row["timings"] = stats.get("timings")
    row["recheck_verdict"] = (stats.get("recheck") or {}).get("verdict")
    row["recheck_geometry_pass"] = all(
        (stats.get("recheck_geometry") or {}).get(key) is True
        for key in ("endpoint_invariant", "joins_C0_C1_direction", "transition_radius_pass",
                    "xy_projection_preserved", "single_elevation_structure"))
    row["budget_checkpoints"] = stats.get("budget_checkpoints")
    row["coverage"] = stats.get("coverage")
    row["candidates_by_window_kind"] = stats.get("candidates_by_window_kind")
    row["evaluated_by_window_kind"] = stats.get("evaluated_candidates_by_window_kind")
    row["executed_by_window_kind"] = stats.get("executed_moves_by_window_kind")
    row["generation_accounting"] = stats.get("generation_accounting")
    row["tag"] = path.parent.name[len(group):].lstrip("_") or None
    ledger_path = path.parent / "ledger.json"
    if ledger_path.is_file():
        # The driver copies only a declared subset of ledger fields into
        # summary.json; the v8 window-kind and cap accounting lives in
        # ledger.json, so it is merged here (never re-derived).
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        for key in ("generation_accounting", "candidates_by_window_kind",
                    "generated_candidates_by_window_kind",
                    "evaluated_candidates_by_window_kind",
                    "full_accepted_candidates_by_window_kind",
                    "executed_moves_by_window_kind",
                    "first_elevation_moves_by_window_kind",
                    "relocation_moves_by_window_kind",
                    "final_path_window_transition_count", "final_logical_ramp_count",
                    "final_physical_fragment_count", "stage_length_cap_mm",
                    "stage_length_cap_checks", "stage_length_cap_rejections",
                    "stage_length_cap_rejected_step_length_mm",
                    "stage_length_cap_rejections_by_action",
                    "stage_length_cap_headroom_mm", "stage_length_cap_used_percent",
                    "path_window_first_elevation_net_reduction",
                    "path_window_relocation_net_reduction",
                    "path_window_step_length_delta_mm", "line_window_step_length_delta_mm"):
            if key in ledger and row.get(key) is None:
                row[key] = ledger[key]
    return row


def write(name, payload):
    target = OUT / "comparison"
    target.mkdir(parents=True, exist_ok=True)
    (target / (name + ".json")).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("wrote", name, flush=True)
    return target / (name + ".json")


def write_csv(name, rows, columns):
    target = OUT / "comparison"
    target.mkdir(parents=True, exist_ok=True)
    path = target / (name + ".csv")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([row.get(column) for column in columns])
    print("wrote", path.name, flush=True)
    return path


def section_p2():
    """G0 (referenced v7 T0 / v6 E2) versus G1 (path windows), all budgets."""
    rows = []
    for mode in ("N", "R"):
        for budget in (720, 1440, 2880):
            for label, round_name, group in (
                    ("G0_LINE_ONLY", "v7", "V7_T0_%s%d" % (mode, budget)),
                    ("G1_PATH_WINDOWS", "v8", "V8_G1_%s%d" % (mode, budget))):
                row = load(round_name, group)
                row["arm"] = label
                row["mode"] = mode
                row["budget"] = budget
                rows.append(row)
        for label, round_name, group in (
                ("G0_LINE_ONLY", "v7", "V7_T0_%sC2880" % mode),
                ("G1_PATH_WINDOWS", "v8", "V8_G1_%sC2880" % mode)):
            row = load(round_name, group)
            row["arm"] = label
            row["mode"] = mode
            row["budget"] = 2880
            row["challenge"] = True
            rows.append(row)
    cells = []
    for mode in ("N", "R"):
        for budget in (720, 1440, 2880):
            for challenge in (False, True):
                bucket = [r for r in rows if r["mode"] == mode and r["budget"] == budget
                          and bool(r.get("challenge")) == challenge]
                zero = next((r for r in bucket if r["arm"] == "G0_LINE_ONLY"), None)
                one = next((r for r in bucket if r["arm"] == "G1_PATH_WINDOWS"), None)
                if not zero or not one:
                    continue
                cell = dict(mode=mode, budget=budget, challenge=challenge,
                            g0=zero, g1=one)
                if zero["status"] == "PRESENT" and one["status"] == "PRESENT":
                    cell["delta_final_pairs"] = (one["final_collision_pairs"]
                                                 - zero["final_collision_pairs"])
                    cell["delta_stage_length_mm"] = (one["stage_length_delta_mm"]
                                                     - zero["stage_length_delta_mm"])
                    cell["delta_moves"] = one["accepted_moves"] - zero["accepted_moves"]
                    cell["g1_better"] = one["final_collision_pairs"] < zero["final_collision_pairs"]
                cells.append(cell)
    summary = dict(cells=cells, rows=rows,
                   verdict=("G1 improves the same-budget whole-layout result in %d of %d cells"
                            % (sum(1 for c in cells if c.get("g1_better")),
                               sum(1 for c in cells if "g1_better" in c))))
    write("p2_g0_vs_g1", summary)
    write_csv("p2_g0_vs_g1", rows,
              ["arm", "mode", "budget", "challenge", "status", "final_collision_pairs",
               "candidate_evaluations", "accepted_moves", "first_elevations", "relocations",
               "stage_length_delta_mm", "final_transition_count",
               "final_path_window_transition_count", "stop_reason", "recheck_verdict",
               "source_root"])
    return summary


def section_g1_defect():
    """The G1 arms that ran with the boundary-snap defect vs the fixed re-runs."""
    rows = []
    for mode in ("N", "R"):
        for budget in (720, 1440, 2880):
            for challenge in (False, True):
                group = "V8_G1_%s%s%d" % (mode, "C" if challenge else "", budget)
                buggy = load("v8", group)
                fixed = load("v8", group)
                rows.append(dict(group=group, mode=mode, budget=budget, challenge=challenge,
                                 defective_folder=buggy.get("status"),
                                 defective_tag=buggy.get("tag"),
                                 fixed_tag=fixed.get("tag"),
                                 note=("the same compare helper resolves the fixed re-run first; the "
                                       "defective numbers are read separately from the untagged "
                                       "folder by the verification run")))
    return dict(rows=rows)


def section_neutrality():
    """The v8 code must reproduce the historical G0 result bit for bit."""
    pairs = [("v8_neutrality", "V8_G0_NEUTRALITY_R2880", "v7", "V7_T0_R2880"),
             ("v8_neutrality", "V8_G0_NEUTRALITY_R720", "v7", "V7_T0_R720"),
             ("v8_neutrality", "V8_G0_NEUTRALITY_RC2880", "v7", "V7_T0_RC2880")]
    rows = []
    for new_round, new_group, old_round, old_group in pairs:
        new = load(new_round, new_group)
        old = load(old_round, old_group)
        row = dict(new_group=new_group, old_group=old_group,
                   new_status=new["status"], old_status=old["status"])
        if new["status"] == "PRESENT" and old["status"] == "PRESENT":
            # Only fields that BOTH ledgers carry can be compared: the v8 ledger
            # adds new bookkeeping (path windows, logical ramps, cap counters)
            # that the historical summaries simply do not have. Their absence is
            # recorded as an additive field, never as a behavioural difference.
            comparable = [field for field in FIELDS
                          if new.get(field) is not None and old.get(field) is not None]
            additive = [field for field in FIELDS
                        if new.get(field) is not None and old.get(field) is None]
            for field in comparable:
                row["same_" + field] = new[field] == old[field]
            row["comparable_fields"] = len(comparable)
            row["new_additive_fields"] = additive
            row["identical_all_comparable_fields"] = all(
                row["same_" + field] for field in comparable)
            new_folder, _ = group_folder(new_round, new_group)
            old_folder, _ = group_folder(old_round, old_group)
            row["new_folder"] = str(new_folder)
            row["old_folder"] = str(old_folder)
            row["step_trace_identical"] = compare_step_trace(new_folder / "decisions.json",
                                                             old_folder / "decisions.json")
            new_sets = json.loads((new_folder / "collision_sets.json").read_text(encoding="utf-8"))
            old_sets = json.loads((old_folder / "collision_sets.json").read_text(encoding="utf-8"))
            # the v8 ledger adds fields; the pair sets and the length ledger are
            # the historical comparison keys and must match exactly
            row["near_distance_sets_identical"] = all(
                new_sets.get(key) == old_sets.get(key) for key in
                ("initial_collision_pairs", "final_collision_pairs", "initial_unresolved_pairs",
                 "final_unresolved_pairs", "elevated_route_ids", "relocated_route_ids",
                 "returned_route_ids", "ledger_step_length_delta_mm",
                 "ledger_stage_length_delta_mm", "ledger_final_total_length_mm",
                 "ledger_final_extra_length_vs_planar_mm"))
            row["final_routes_identical"] = route_files_identical(
                new_folder / "final_routes.json", old_folder / "final_routes.json")
        rows.append(row)
    summary = dict(rows=rows,
                   verdict=("neutral" if all(r.get("identical_all_comparable_fields")
                                             and r.get("step_trace_identical")
                                             and r.get("near_distance_sets_identical")
                                             and r.get("final_routes_identical") for r in rows)
                             else "NOT NEUTRAL - investigate"))
    write("neutrality_v8_code", summary)
    return summary


def _step_signature(step):
    return dict(step_index=step.get("step_index"), target_pair=step.get("target_pair"),
                status=step.get("status"), movement=step.get("movement"),
                moved_route_id=step.get("moved_route_id"),
                selected_candidate_index=step.get("selected_candidate_index"),
                selected_window_kind=step.get("selected_window_kind", "LINE_WINDOW_G0"),
                old_collisions_removed=step.get("old_collisions_removed"),
                new_collisions_created=step.get("new_collisions_created"),
                net_collision_reduction=step.get("net_collision_reduction"),
                step_length_delta_mm=step.get("step_length_delta_mm"),
                global_collision_pairs_after=step.get("global_collision_pairs_after"),
                candidate_evaluations_after=step.get("candidate_evaluations_after"))


def compare_step_trace(new_path, old_path):
    if not (new_path.is_file() and old_path.is_file()):
        return None
    new = json.loads(new_path.read_text(encoding="utf-8"))
    old = json.loads(old_path.read_text(encoding="utf-8"))
    if len(new) != len(old):
        return False
    return all(_step_signature(a) == _step_signature(b) for a, b in zip(new, old))


def route_files_identical(new_path, old_path):
    if not (new_path.is_file() and old_path.is_file()):
        return None
    return json.loads(new_path.read_text(encoding="utf-8")) == json.loads(
        old_path.read_text(encoding="utf-8"))


def section_p3():
    """BASE_E2 / A_FAMILY x max_targets 200/2000 x N/R x budgets, with references."""
    arms = [("BASE_E2", "P3_BASE_E2_T200", "v7", "V7_T0"),
            ("BASE_E2", "P3_BASE_E2_T2000", "v7", "V7_T1"),
            ("A_FAMILY", "P3_A_FAMILY_T200", "ideas", "IDEA_A_FAMILY"),
            ("A_FAMILY", "P3_A_FAMILY_T2000", "p3", "P3_A_FAMILY_T2000")]
    rows = []
    for family, new_prefix, fallback_round, fallback_prefix in arms:
        for mode in ("N", "R"):
            for budget in (720, 1440, 2880):
                group = new_prefix + "_" + mode + str(budget)
                row = load("p3", group)
                if row["status"] == "MISSING":
                    row = load(fallback_round, fallback_prefix + "_" + mode + str(budget))
                    row["group"] = group
                    row["reused_reference"] = True
                row["arm"] = family
                row["mode"] = mode
                row["budget"] = budget
                rows.append(row)
            group = new_prefix + "_" + mode + "C2880"
            row = load("p3", group)
            if row["status"] == "MISSING":
                row = load(fallback_round, fallback_prefix + "_" + mode + "C2880")
                row["group"] = group
                row["reused_reference"] = True
            row["arm"] = family
            row["mode"] = mode
            row["budget"] = 2880
            row["challenge"] = True
            rows.append(row)
    for row in rows:
        if row["status"] != "PRESENT":
            continue
        cap = row.get("appended_candidate_budget") or 0
        used = row.get("candidate_evaluations") or 0
        row["budget_ceiling"] = cap
        row["budget_used"] = used
        row["budget_used_percent"] = round(100. * used / cap, 2) if cap else None
        row["target_limit_hit"] = row.get("stop_reason") == "TARGET_LIMIT"
        row["budget_exhausted"] = row.get("stop_reason") == "CANDIDATE_BUDGET_EXHAUSTED"
        row["actual_evaluation_aligned"] = (used == cap)
    def cell(family, mode, budget, challenge):
        for row in rows:
            if (row["arm"] == family and row["mode"] == mode and row["budget"] == budget
                    and bool(row.get("challenge")) == challenge):
                return row
        return None
    matrix = []
    for mode in ("N", "R"):
        for budget in (720, 1440, 2880):
            for challenge in (False, True):
                for limit in (200, 2000):
                    base_row = cell("BASE_E2", mode, budget, challenge) if limit == 200 else None
                    entry = dict(mode=mode, budget=budget, challenge=challenge, max_targets=limit,
                                 base_e2=(cell("BASE_E2", mode, budget, challenge)
                                          if limit == 200 else None),
                                 a_family=(cell("A_FAMILY", mode, budget, challenge)
                                           if limit == 200 else None))
                    matrix.append(entry)
    by_limit = {}
    for limit in (200, 2000):
        for family in ("BASE_E2", "A_FAMILY"):
            key = "%s_T%d" % (family, limit)
            subset = [r for r in rows if r["arm"] == family and (r.get("max_targets") or 200) == limit
                      and r["status"] == "PRESENT"]
            if subset:
                by_limit[key] = dict(
                    cells=len(subset),
                    main_r2880=next((r["final_collision_pairs"] for r in subset
                                     if r["mode"] == "R" and r["budget"] == 2880
                                     and not r.get("challenge")), None),
                    actual_evaluations_r2880=next((r["candidate_evaluations"] for r in subset
                                                   if r["mode"] == "R" and r["budget"] == 2880
                                                   and not r.get("challenge")), None),
                    target_limit_hits=sum(1 for r in subset if r["target_limit_hit"]),
                    budget_full_uses=sum(1 for r in subset if r["budget_exhausted"]),
                    stage_length_delta_r2880=next((r["stage_length_delta_mm"] for r in subset
                                                   if r["mode"] == "R" and r["budget"] == 2880
                                                   and not r.get("challenge")), None))
    summary = dict(rows=rows, by_limit=by_limit, matrix=matrix)
    write("p3_family_and_target_limit", summary)
    write_csv("p3_family_and_target_limit", rows,
              ["arm", "mode", "budget", "challenge", "status", "max_targets",
               "candidate_evaluations", "budget_used_percent", "stop_reason", "target_limit_hit",
               "final_collision_pairs", "accepted_moves", "stage_length_delta_mm",
               "final_elevated_route_count", "reused_reference", "source_root"])
    return summary


def p4_cells():
    rows = []
    for family, prefix in (("BASE_E2", "P4_BASE_E2_CAP"), ("A_FAMILY", "P4_A_FAMILY_CAP")):
        for cap in (24, 40, 60):
            for mode in ("N", "R"):
                for challenge in (False, True):
                    group = "%s%d_%s%s2880" % (prefix, cap, mode, "C" if challenge else "")
                    row = load("p4", group)
                    row["arm"] = family
                    row["cap_mm"] = float(cap)
                    row["mode"] = mode
                    row["challenge"] = challenge
                    rows.append(row)
    return rows


def section_p4():
    """Length-cap experiment plus the uncapped references from P3."""
    rows = p4_cells()
    references = []
    for family, round_name, prefix in (("BASE_E2", "v7", "V7_T1"),
                                       ("A_FAMILY", "p3", "P3_A_FAMILY_T2000")):
        for mode in ("N", "R"):
            for challenge in (False, True):
                group = "%s_%s%s2880" % (prefix, mode, "C" if challenge else "")
                row = load(round_name, group)
                row["arm"] = family
                row["cap_mm"] = None
                row["mode"] = mode
                row["challenge"] = challenge
                row["uncapped_reference"] = True
                references.append(row)
    for row in rows + references:
        if row["status"] != "PRESENT":
            continue
        row["cap_binding"] = (row.get("stage_length_cap_rejections") or 0) > 0
        row["cap_headroom_mm"] = row.get("stage_length_cap_headroom_mm")
        row["structure_count"] = row.get("final_transition_count")
        row["path_window_count"] = row.get("final_path_window_transition_count")
    summary = dict(capped=rows, uncapped_references=references)
    write("p4_length_cap", summary)
    write_csv("p4_length_cap", rows + references,
              ["arm", "mode", "challenge", "cap_mm", "status", "final_collision_pairs",
               "stage_length_delta_mm", "stage_length_cap_rejections", "stage_length_cap_checks",
               "stage_length_cap_headroom_mm", "candidate_evaluations", "accepted_moves",
               "stop_reason", "final_elevated_route_count", "structure_count"])
    return summary


def section_pe():
    """EXTRA queue 1: idea E (multi-anchor) x max_targets 200 / 2000."""
    rows = []
    for mode in ("N", "R"):
        for budget in (720, 1440, 2880):
            for challenge in (False, True):
                if challenge and budget != 2880:
                    continue
                suffix = mode + ("C" if challenge else "") + str(budget)
                for arm, limit, round_name, prefix in (
                        ("E_T200", 200, "ideas", "IDEA_E"),
                        ("E_T2000", 2000, "pe", "PE_E_T2000")):
                    group = "PE_%s_%s" % (arm, suffix)
                    row = load("pe", group)
                    if row["status"] == "MISSING":
                        row = load(round_name, prefix + "_" + suffix)
                        row["group"] = group
                        row["reused_reference"] = True
                    row["arm"] = arm
                    row["max_targets"] = limit
                    row["mode"] = mode
                    row["budget"] = budget
                    if challenge:
                        row["challenge"] = True
                    if row["status"] == "PRESENT":
                        cap = row.get("appended_candidate_budget") or 0
                        used = row.get("candidate_evaluations") or 0
                        row["budget_used_percent"] = round(100. * used / cap, 2) if cap else None
                        row["target_limit_hit"] = row.get("stop_reason") == "TARGET_LIMIT"
                    rows.append(row)
    summary = dict(rows=rows,
                   question=("was idea E's early stop caused by the 200 target-attempt limit or by "
                             "the mechanism itself?"),
                   wording=("the two arms differ ONLY in max_targets; the E definition "
                            "(multi-anchor witness) is unchanged"))
    write("pe_multi_anchor_limit", summary)
    write_csv("pe_multi_anchor_limit", rows,
              ["arm", "max_targets", "mode", "budget", "challenge", "status",
               "candidate_evaluations", "budget_used_percent", "stop_reason", "target_limit_hit",
               "final_collision_pairs", "accepted_moves", "stage_length_delta_mm",
               "reused_reference"])
    return summary


def section_p5():
    """Controlled serial timing: cache off/on, three alternating repeats each."""
    rows = []
    for arm in ("OFF", "ON"):
        for seq in (1, 2, 3):
            group = "P5_CACHE_%s_R1440_seq%d" % (arm, seq)
            row = load("p5", group)
            row["arm"] = arm
            row["sequence"] = seq
            if row["status"] == "PRESENT":
                timings = row.get("timings") or {}
                row["initial_pair_scan_seconds"] = timings.get("initial_pair_scan_seconds")
                row["assignment_seconds"] = timings.get("assignment_seconds")
                row["runtime_seconds"] = timings.get("runtime_seconds")
                row["run_seconds_including_recheck"] = timings.get("run_seconds_including_recheck")
                row["recheck_and_io_seconds"] = (
                    None if row["run_seconds_including_recheck"] is None
                    or row["runtime_seconds"] is None
                    else row["run_seconds_including_recheck"] - row["runtime_seconds"])
            rows.append(row)
    def stats(arm, key):
        values = sorted(r[key] for r in rows
                        if r["arm"] == arm and r["status"] == "PRESENT" and r[key] is not None)
        if not values:
            return None
        return dict(n=len(values), min=values[0], median=values[len(values) // 2], max=values[-1])
    summary = dict(rows=rows,
                   median_runtime_seconds={arm: stats(arm, "runtime_seconds")
                                           for arm in ("OFF", "ON")},
                   median_run_seconds_including_recheck={
                       arm: stats(arm, "run_seconds_including_recheck") for arm in ("OFF", "ON")},
                   median_assignment_seconds={arm: stats(arm, "assignment_seconds")
                                              for arm in ("OFF", "ON")},
                   median_scan_seconds={arm: stats(arm, "initial_pair_scan_seconds")
                                        for arm in ("OFF", "ON")},
                   consistency=dict(
                       cache_hits={arm: sorted(r.get("decision_cache_hits") for r in rows
                                               if r["arm"] == arm and r["status"] == "PRESENT")
                                   for arm in ("OFF", "ON")},
                       final_pairs={arm: sorted(r.get("final_collision_pairs") for r in rows
                                                if r["arm"] == arm and r["status"] == "PRESENT")
                                    for arm in ("OFF", "ON")},
                       stage_length_delta={arm: sorted(r.get("stage_length_delta_mm") for r in rows
                                                        if r["arm"] == arm
                                                        and r["status"] == "PRESENT")
                                           for arm in ("OFF", "ON")}))
    write("p5_serial_timing", summary)
    write_csv("p5_serial_timing", rows,
              ["arm", "sequence", "status", "initial_pair_scan_seconds", "assignment_seconds",
               "runtime_seconds", "run_seconds_including_recheck", "recheck_and_io_seconds",
               "candidate_evaluations", "decision_cache_hits", "final_collision_pairs",
               "accepted_moves", "stage_length_delta_mm", "recheck_verdict"])
    return summary


def main():
    wanted = WANTED or SECTIONS
    result = {}
    if "p2" in wanted:
        result["p2"] = section_p2()
    if "neutrality" in wanted:
        result["neutrality"] = section_neutrality()
    if "p3" in wanted:
        result["p3"] = section_p3()
    if "p4" in wanted:
        result["p4"] = section_p4()
    if "p5" in wanted:
        result["p5"] = section_p5()
    if "pe" in wanted:
        result["pe"] = section_pe()
    print(json.dumps({k: (v.get("verdict") if isinstance(v, dict) else None)
                      for k, v in result.items()}, indent=2, default=str))


if __name__ == "__main__":
    main()
