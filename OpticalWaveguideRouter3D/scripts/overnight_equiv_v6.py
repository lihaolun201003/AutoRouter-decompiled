"""E0 vs E1 identity check for v6: does the cheap ordering alone change anything?"""
import sys, json, hashlib
from pathlib import Path


def key(d):
    led = json.loads((d / "ledger.json").read_text(encoding="utf-8"))
    sets = json.loads((d / "collision_sets.json").read_text(encoding="utf-8"))
    curve = json.loads((d / "curve.json").read_text(encoding="utf-8"))
    traj = [(r["step"], round(r["collision_pair_count"], 9), r["candidate_evaluations"]) for r in curve]
    ph = hashlib.sha256(";".join("%d-%d" % tuple(p) for p in sorted(map(tuple, sets["final_collision_pairs"]))).encode()).hexdigest()
    return dict(final_collision_pairs=led["final_collision_pair_count"], accepted_moves=led["accepted_moves"],
                candidate_evaluations=led["candidate_evaluations"], stage_length_delta_mm=led["stage_length_delta_mm"],
                final_transition_count=led["final_transition_count"], trajectory=traj, pair_hash=ph,
                target_attempts=led["target_attempts"], stop_reason=led["stop_reason"])


def main():
    root = Path(sys.argv[1]).resolve(); out = Path(sys.argv[2]).resolve()
    v6 = out / "v6"
    rows = []; all_same = True
    for budget in (720, 1440, 2880):
        for mode in ("N", "R"):
            e0 = key(v6 / ("V6_E0_" + mode + str(budget)))
            e1 = key(v6 / ("V6_E1_" + mode + str(budget)))
            same = e0 == e1
            all_same = all_same and same
            rows.append(dict(mode=mode, budget=budget, identical=same,
                             e0=e0["final_collision_pairs"], e1=e1["final_collision_pairs"],
                             e0_moves=e0["accepted_moves"], e1_moves=e1["accepted_moves"],
                             e0_stage=e0["stage_length_delta_mm"], e1_stage=e1["stage_length_delta_mm"],
                             pair_hash_equal=e0["pair_hash"] == e1["pair_hash"],
                             trajectory_equal=e0["trajectory"] == e1["trajectory"]))
    doc = dict(criterion=("E0 and E1 differ only in the EVALUATION ORDER of the already generated pool; "
                          "if they are identical everywhere, the E0->E1 change comes from the budget boundary "
                          "and not from the ordering"),
               e0_source=("outputs/overnight_3d_ideas/v6/V6_E0_* are verbatim copies of the v5 LEGACY groups, "
                          "which the v5 equivalence check proved identical to the reviewed v4 groups"),
               all_identical=all_same, rows=rows)
    (out / "equiv").mkdir(parents=True, exist_ok=True)
    (out / "equiv" / "v6_e0_vs_e1.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    for r in rows:
        print("budget=%d mode=%s identical=%s e0=%d e1=%d" % (r["budget"], r["mode"], r["identical"], r["e0"], r["e1"]))
    print("ALL_IDENTICAL", all_same)


if __name__ == "__main__":
    main()
