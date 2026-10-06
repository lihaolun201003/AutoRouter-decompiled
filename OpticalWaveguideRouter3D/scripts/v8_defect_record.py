"""Record the superseded G1 arms that ran with the boundary-snap defect.

The first G1 batch is kept as evidence of the defect, never deleted:
  * every arm's ledger is read from the UNTAGGED folder,
  * the ENDPOINT_CHANGED rejections and the deferred K16 prefixes are counted,
  * the fixed re-run (folder suffixed _boundaryfix) is compared against it.

Usage: python -B scripts/v8_defect_record.py PROJECT OUTDIR
"""
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
GROUPS = ["V8_G1_%s%s%d" % (mode, "C" if challenge else "", budget)
          for mode in ("N", "R") for budget in (720, 1440, 2880) for challenge in (False, True)]


def read(folder, name):
    path = folder / name
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def main():
    rows = []
    for group in GROUPS:
        defective = OUT / "v8" / group
        fixed = OUT / "v8" / (group + "_boundaryfix")
        ledger = read(defective, "ledger.json")
        decision = read(defective, "decisions.json")
        fixed_stats = None
        path = fixed / "summary.json"
        if path.is_file():
            fixed_stats = json.loads(path.read_text(encoding="utf-8"))["stats"]
        row = dict(group=group, defective_folder=str(defective), fixed_folder=str(fixed),
                   defective_present=ledger is not None, fixed_present=fixed_stats is not None)
        if ledger:
            row["defective_final_pairs"] = ledger["final_collision_pair_count"]
            row["defective_moves"] = ledger["accepted_moves"]
            row["defective_evaluations"] = ledger["candidate_evaluations"]
            row["defective_endpoint_changed_rejections"] = (
                ledger["basic_rejection_reason_counts"].get("ENDPOINT_CHANGED", 0))
            row["defective_deferred_steps"] = ledger["deferred_prefix_no_winner"]
            row["defective_target_attempts"] = ledger["target_attempts"]
            row["defective_executed_by_kind"] = ledger.get("executed_moves_by_window_kind")
        if decision is not None:
            rejected = sum(1 for step in decision for va in step["victim_attempts"]
                           for entry in va.get("candidates", [])
                           if "ENDPOINT_CHANGED" in (entry.get("basic_reasons") or []))
            row["defective_endpoint_changed_from_decisions"] = rejected
        if fixed_stats:
            row["fixed_final_pairs"] = fixed_stats["final_collision_pairs"]
            row["fixed_moves"] = fixed_stats["accepted_moves"]
            row["fixed_evaluations"] = fixed_stats["candidate_evaluations"]
            row["fixed_executed_by_kind"] = None
            fixed_ledger = read(fixed, "ledger.json")
            if fixed_ledger:
                row["fixed_executed_by_kind"] = fixed_ledger.get("executed_moves_by_window_kind")
                row["fixed_endpoint_changed_rejections"] = (
                    fixed_ledger["basic_rejection_reason_counts"].get("ENDPOINT_CHANGED", 0))
                row["fixed_deferred_steps"] = fixed_ledger["deferred_prefix_no_winner"]
        rows.append(row)
    record = dict(
        defect=("split_path_interval produced v=0.9999999999999999 instead of 1.0 when a window "
                "ended exactly at the route total (1 ulp), so the sub-curve endpoint was "
                "interpolated and moved the frozen terminal point by ~1.2e-14 mm; "
                "evaluate_elevation then rejected the candidate with ENDPOINT_CHANGED"),
        fix=("BOUNDARY_SNAP_MM = 1e-9: a sub-interval end within 1e-9 mm of a primitive boundary "
             "is snapped to the boundary itself; regression test "
             "tests/test_path_window_3d.py::test_windows_touching_the_route_ends_keep_the_exact_frozen_endpoints"),
        superseded_runs_are_kept_as_evidence=True,
        rows=rows)
    target = OUT / "comparison"
    target.mkdir(parents=True, exist_ok=True)
    (target / "p2_g1_defect_record.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    for row in rows:
        print(group := row["group"], "defect pairs", row.get("defective_final_pairs"),
              "endpoint_changed", row.get("defective_endpoint_changed_rejections"),
              "deferred", row.get("defective_deferred_steps"),
              "| fixed pairs", row.get("fixed_final_pairs"),
              "endpoint_changed", row.get("fixed_endpoint_changed_rejections"))


if __name__ == "__main__":
    main()
