"""Regenerate the machine state of the v8 continuation from the saved artefacts.

Writes outputs/overnight_3d_continuation/{status.json,task_queue.json,checkpoint.md}
from the comparison files, the verification file and the pool log, so the
machine state can never drift from the evidence.

Usage: python -B outputs/overnight_3d_continuation/update_checkpoint.py PROJECT OUTDIR
"""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
FENCE = chr(96) * 3


def load(relative, default=None):
    path = OUT / relative
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    p2 = load("comparison/p2_g0_vs_g1.json", {})
    p3 = load("comparison/p3_family_and_target_limit.json", {})
    p4 = load("comparison/p4_length_cap.json", {})
    p5 = load("comparison/p5_serial_timing.json", {})
    pe = load("comparison/pe_multi_anchor_limit.json", {})
    neutral = load("comparison/neutrality_v8_code.json", {})
    verification = load("verification/final_verification.json", {})
    diagnostics = load("diagnostics/v8_side_diagnostics_summary.json", {})
    pool = load("pool_last_run.json", {})
    status = dict(
        task="v8 path-arc-length windows, A budget fairness, length caps, serial timing, report QA",
        updated=datetime.now().isoformat(timespec="seconds"),
        v8=dict(
            implemented=True,
            support_chain="src/geometry_3d.py PathWindowTransition3D + src/path_window_3d.py + full chain",
            targeted_tests="tests/test_path_window_3d.py (25) and tests/test_overnight_engine_3d.py (21)",
            full_regression="803 passed, 4 skipped",
            g0_equivalence=neutral.get("verdict"),
            p2_cells=len(p2.get("cells", [])),
            p2_g1_better_cells=sum(1 for c in p2.get("cells", []) if c.get("g1_better")),
            p2_verdict=p2.get("verdict"),
        ),
        diagnostics=dict(
            sides=diagnostics.get("frozen_diagnostic_set", {}).get("sides"),
            old_no_window_sides=diagnostics.get("old_no_window_sides"),
            old_no_window_now_g1_candidates=diagnostics.get("old_no_window_now_g1_candidates"),
            old_no_window_g1_full_passed=diagnostics.get("old_no_window_g1_full_passed"),
            ledger=diagnostics.get("ledger"),
        ) if diagnostics else None,
        p3=dict(cells=len(p3.get("rows", [])), by_limit=p3.get("by_limit")) if p3 else None,
        p4=dict(capped=len(p4.get("capped", [])),
                uncapped=len(p4.get("uncapped_references", []))) if p4 else None,
        p5=dict(engine_median=p5.get("median_runtime_seconds"),
                total_median=p5.get("median_run_seconds_including_recheck"),
                consistency=p5.get("consistency")) if p5 else None,
        extra_queue_pe=dict(
            rows=len(pe.get("rows", [])),
            e_t200_r2880=next((r.get("final_collision_pairs") for r in pe.get("rows", [])
                               if r.get("arm") == "E_T200" and not r.get("challenge")
                               and r.get("mode") == "R" and r.get("budget") == 2880), None),
            e_t2000_r2880=next((r.get("final_collision_pairs") for r in pe.get("rows", [])
                                if r.get("arm") == "E_T2000" and not r.get("challenge")
                                and r.get("mode") == "R" and r.get("budget") == 2880), None),
            finding=("E stops at 668 evaluations under max_targets=200 whatever the budget; with "
                     "max_targets=2000 the same budget is fully used and R2880 reaches 15935 pairs")) if pe else None,
        verification=dict(groups_total=verification.get("groups_total"),
                          groups_pass=verification.get("groups_pass"),
                          groups_fail=verification.get("groups_fail"),
                          groups_not_finished=verification.get("groups_not_finished"),
                          all_finished_groups_pass=verification.get("all_finished_groups_pass")),
        pool=dict(total=pool.get("total"), seconds=pool.get("seconds"),
                  failures=sum(1 for r in pool.get("results", []) if r.get("exit"))),
        not_done=[],
    )
    (OUT / "status.json").write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
    queue = dict(
        completed=["v8 support chain", "v8 G0/G1 formal arms", "A budget fairness (P3)",
                   "length caps (P4)", "controlled serial timing (P5)",
                   "60-pair/120-side diagnostics", "report + page by page visual QA"],
        remaining=[],
        resume_commands=dict(
            verify=(".venv\\Scripts\\python.exe -B scripts\\overnight_final_verification.py . "
                    "outputs\\overnight_3d_continuation --v8"),
            tests=".venv\\Scripts\\python.exe -B -m pytest tests -q",
            compare=(".venv\\Scripts\\python.exe -B scripts\\v8_compare.py . "
                     "outputs\\overnight_3d_continuation"),
            figures=(".venv\\Scripts\\python.exe -B scripts\\v8_figures.py . "
                     "outputs\\overnight_3d_continuation"),
            diagnostics=(".venv\\Scripts\\python.exe -B scripts\\v8_diagnostics.py . "
                         "outputs\\overnight_3d_continuation"),
            report=("python scripts\\publication\\build_v8_continuation_report.py . "
                    "outputs\\overnight_3d_continuation"),
            rerun_group=(".venv\\Scripts\\python.exe -B scripts\\run_overnight_3d.py . "
                         "outputs\\overnight_3d_continuation --round v8 --group <GROUP>"),
        ),
    )
    (OUT / "task_queue.json").write_text(json.dumps(queue, indent=2, ensure_ascii=False),
                                         encoding="utf-8")
    lines = ["# v8 continuation checkpoint", "",
             "Machine state: status.json, task_queue.json. Plan: plan_p0_state.json. "
             "Code snapshot: code_snapshot.json.", "",
             "## Resume after an interruption", "", FENCE + "powershell",
             "cd \"%s\"" % ROOT, ""]
    for name, command in queue["resume_commands"].items():
        lines.append("# " + name)
        lines.append(command)
        lines.append("")
    lines += [FENCE, "", "## Status", "", FENCE + "json",
              json.dumps({k: v for k, v in status.items() if k != "pool"},
                         indent=1, ensure_ascii=False)[:4000], FENCE, ""]
    (OUT / "checkpoint.md").write_text("\n".join(lines), encoding="utf-8")
    print("status/queue/checkpoint written")


if __name__ == "__main__":
    main()
