"""Post-process the saved 120-side diagnostic into the mechanism breakdown.

Reads diagnostics/v8_side_diagnostics.json (never re-runs the acceptance work)
and answers, per side and in total:
  * how many old no-window sides get candidates under G0 / G1
  * of those that do not: how many are CURVATURE-rejected (an exact bound, with
    the arcs they cover) and how many have no legal interval long enough for ANY
    transition (a hard geometric limit of one rise + one fall at the route ends)
  * where the K16 prefix goes: line windows vs path windows

Usage: python -B scripts/v8_diagnostics_extra.py PROJECT OUTDIR
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
DIAG = OUT / "diagnostics"


def bucket(row):
    stats = (row["G1"].get("generation_stats") or {})
    if row["G1"]["generated_candidates"] > 0:
        return "GOT_CANDIDATES"
    if row["G1"]["curvature_rejected"] > 0:
        return "CURVATURE_REJECTED_ONLY"
    if stats.get("path_window_length_does_not_fit", 0) > 0:
        return "NO_INTERVAL_LONG_ENOUGH"
    if (stats.get("path_window_no_legal_interval") or 0) > 0:
        return "EMPTY_LEGAL_INTERVAL"
    return "OTHER_NO_CANDIDATE"


def main():
    document = json.loads((DIAG / "v8_side_diagnostics.json").read_text(encoding="utf-8"))
    rows = document["rows"]
    old = [r for r in rows if r["v4_outcome"] == "NO_LEGAL_WINDOW_UNDER_CURRENT_RULES"]
    breakdown = Counter(bucket(r) for r in old)
    detail = []
    for r in old:
        stats = (r["G1"].get("generation_stats") or {})
        detail.append(dict(moved_route_id=r["moved_route_id"], target_pair=r["target_pair"],
                           category=r["category"], mechanism=bucket(r),
                           g0_candidates=r["G0"]["generated_candidates"],
                           g1_candidates=r["G1"]["generated_candidates"],
                           g1_curvature_rejected=r["G1"]["curvature_rejected"],
                           length_does_not_fit=stats.get("path_window_length_does_not_fit"),
                           legal_interval_mm=stats.get("legal_interval_mm"),
                           minimum_run_needed_mm=stats.get("zero_curvature_minimum_run_mm"),
                           planar_total_length_mm=stats.get("planar_total_length_mm"),
                           v4_failure=r["G0"].get("failures")))
    prefix = dict(
        g0=dict(Counter(k for r in rows for k, v in
                        ((r["G0"].get("k16_prefix") or {}).get("prefix_by_kind") or {}).items()
                        for _ in range(v))),
        g1=dict(Counter(k for r in rows for k, v in
                        ((r["G1"].get("k16_prefix") or {}).get("prefix_by_kind") or {}).items()
                        for _ in range(v))),
        sides_with_path_windows_in_prefix=sum(
            1 for r in rows if (((r["G1"].get("k16_prefix") or {}).get("prefix_by_kind") or {})
                                .get("PATH_WINDOW_G1", 0) > 0)),
        sides_with_prefix_only_path_windows=sum(
            1 for r in rows
            if (((r["G1"].get("k16_prefix") or {}).get("prefix_by_kind") or {})
                .get("PATH_WINDOW_G1", 0) > 0
                and ((r["G1"].get("k16_prefix") or {}).get("prefix_by_kind") or {})
                .get("LINE_WINDOW_G0", 0) == 0)),
        total_sides=len(rows))
    result = dict(old_no_window_sides=len(old), mechanism_breakdown=dict(breakdown),
                  detail=detail, k16_prefix=prefix,
                  generated_path_windows_total=sum(r["G1"]["generated_path_windows"] for r in rows),
                  curvature_rejected_windows_total=sum(r["G1"]["curvature_rejected"] for r in rows),
                  new_path_windows_total=sum(
                      (r["G1"].get("path_windows_that_are_new_intervals") or 0) for r in rows),
                  wording=("CURVATURE_REJECTED_ONLY means windows were enumerated and every one of them "
                           "failed the exact radius bound; NO_INTERVAL_LONG_ENOUGH means the free planar "
                           "run before the first crossing and/or after the last crossing is shorter than "
                           "the minimum legal transition run, so no window of any kind fits"))
    (DIAG / "v8_side_diagnostics_mechanisms.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "detail"},
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
