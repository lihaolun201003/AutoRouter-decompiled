"""Evidence that the overnight engine LEGACY path reproduces the reviewed v4
groups exactly, so those v4 groups may be cited as the v5 LEGACY baseline.

Compares, for every (mode, budget) pair, the step-level trajectory (step index,
status, live near-distance pair count, evaluations) and the terminal state
(pair count, moves, first elevations, relocations, stage length delta, terminal
collision pair SET hash, stop reason, budget checkpoints). Any mismatch makes the
reuse INVALID and must be reported instead of quietly running the old numbers.

Usage: .venv\\Scripts\\python.exe -B scripts\\overnight_equiv_check.py PROJECT OUTDIR
"""
import sys, json, hashlib
from pathlib import Path


def pair_hash(pairs):
    text = ";".join(str(a) + "-" + str(b) for a, b in sorted(tuple(p) for p in pairs))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_group(directory):
    ledger = json.loads((directory / "ledger.json").read_text(encoding="utf-8"))
    sets = json.loads((directory / "collision_sets.json").read_text(encoding="utf-8"))
    curve = json.loads((directory / "curve.json").read_text(encoding="utf-8"))
    return ledger, sets, curve


def trajectory(curve):
    return [(row["step"], round(row["collision_pair_count"], 9), row["candidate_evaluations"])
            for row in curve]


def main():
    root = Path(sys.argv[1]).resolve(); out = Path(sys.argv[2]).resolve()
    sys.path.insert(0, str(root))
    v4 = root / "outputs/3d_strategy_v4/512_full_layout"
    new = out / "v5"
    groups = []
    for budget in (720, 1440, 2880):
        for mode in ("N", "R"):
            groups.append((mode, budget, v4 / (mode + str(budget)), new / ("V5_LEGACY_" + mode + str(budget))))
    for mode in ("N", "R"):
        groups.append((mode, 2880, None, new / ("V5_LEGACY_" + mode + "C2880")))
    rows = []; ok = True
    for mode, budget, old_dir, new_dir in groups:
        if not (new_dir / "ledger.json").is_file():
            rows.append(dict(mode=mode, budget=budget, group=new_dir.name, status="NOT_FINISHED"))
            continue
        nl, ns, nc = load_group(new_dir)
        record = dict(mode=mode, budget=budget, group=new_dir.name,
                      new=dict(final_collision_pair_count=nl["final_collision_pair_count"],
                               accepted_moves=nl["accepted_moves"],
                               first_elevations=nl["first_elevations"],
                               relocations=nl["relocations"],
                               candidate_evaluations=nl["candidate_evaluations"],
                               stage_length_delta_mm=nl["stage_length_delta_mm"],
                               target_attempts=nl["target_attempts"],
                               stop_reason=nl["stop_reason"],
                               terminal_pair_set_sha256=pair_hash(ns["final_collision_pairs"]),
                               trajectory=trajectory(nc)),
                      new_sha256=hashlib.sha256((new_dir / "final_routes.json").read_bytes()).hexdigest())
        if old_dir is None:
            record["status"] = "NO_V4_COUNTERPART_CHALLENGE_START"
            record["reusable_as_baseline"] = False
            rows.append(record); continue
        ol, os_, oc = load_group(old_dir)
        record["v4"] = dict(final_collision_pair_count=ol["final_collision_pair_count"],
                            accepted_moves=ol["accepted_moves"],
                            first_elevations=ol["first_elevations"],
                            relocations=ol["relocations"],
                            candidate_evaluations=ol["candidate_evaluations"],
                            stage_length_delta_mm=ol["stage_length_delta_mm"],
                            target_attempts=ol["target_attempts"],
                            stop_reason=ol["stop_reason"],
                            terminal_pair_set_sha256=pair_hash(os_["final_collision_pairs"]),
                            trajectory=trajectory(oc))
        checks = {
            "final_collision_pair_count": record["new"]["final_collision_pair_count"] == record["v4"]["final_collision_pair_count"],
            "accepted_moves": record["new"]["accepted_moves"] == record["v4"]["accepted_moves"],
            "first_elevations": record["new"]["first_elevations"] == record["v4"]["first_elevations"],
            "relocations": record["new"]["relocations"] == record["v4"]["relocations"],
            "candidate_evaluations": record["new"]["candidate_evaluations"] == record["v4"]["candidate_evaluations"],
            "stage_length_delta_mm": abs(record["new"]["stage_length_delta_mm"] - record["v4"]["stage_length_delta_mm"]) < 1e-9,
            "target_attempts": record["new"]["target_attempts"] == record["v4"]["target_attempts"],
            "stop_reason": record["new"]["stop_reason"] == record["v4"]["stop_reason"],
            "terminal_pair_set_sha256": record["new"]["terminal_pair_set_sha256"] == record["v4"]["terminal_pair_set_sha256"],
            "step_trajectory": record["new"]["trajectory"] == record["v4"]["trajectory"],
        }
        record["checks"] = checks
        record["status"] = "IDENTICAL" if all(checks.values()) else "DIFFERENT"
        record["reusable_as_baseline"] = all(checks.values())
        if not all(checks.values()): ok = False
        rows.append(record)
    doc = dict(source_v4=str(v4.relative_to(root)), source_new=str(new.relative_to(root)),
               criterion=("the two runs must agree on every compared quantity; only then may the "
                          "reviewed v4 group be cited as the v5 LEGACY baseline"),
               all_reusable=ok, rows=rows)
    (out / "equiv" ).mkdir(parents=True, exist_ok=True)
    (out / "equiv" / "v5_legacy_vs_v4.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    for row in rows:
        extra = "" if "checks" not in row else " " + json.dumps({k: v for k, v in row["checks"].items() if not v})
        print(row["group"], row["status"], extra)
    print("ALL_REUSABLE", ok)


if __name__ == "__main__":
    main()
