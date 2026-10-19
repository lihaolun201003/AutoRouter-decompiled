# Per-experiment strict crossing-policy crosscheck

Independent verification of `crossing_policy='strict'` (authoritative policy, `four_side_1024/abcd/SPEC.md` §2.1) for the 8 frozen primary ABCD experiments and the 2 extension-budget D runs.

Two independent checks per experiment, on each frozen `routes.json`:

1. **Router vs validator pair verdicts** — `python -m four_side_1024.abcd.crosscheck_strict --routes <run>/routes.json --output comparison/crosscheck_<EXP>.json`: every broad-phase route pair is isolated in the router index (`D56Index(crossing_policy='strict')`) and in the authoritative validator (`validate_d56.evaluate_pair(policy='strict')`, which imports no router code); the boolean verdicts, the crossing counts and the window counts must agree, `mismatch=0`.
2. **Independent strict re-audit vs Lead's audit** — `validate_d56.build_report(routes_path, policy='strict')` re-run by validator and compared field by field with the Lead's `audit_strict.json` (22 compared fields incl. `passed`, routed/d56 counts, crossing count, spacing/overlap/touch/window-overlap/double-cross/excessive, window count/max/mean).

Generated: 2026-10-19T09:23:30Z

## 1. Primary ABCD experiments (frozen)

| experiment | routed | strict pass (validator / router index) | crosscheck mismatched pairs | invalid pairs (validator / index) | crossing count (validator vs index) | window count (validator vs index) | max half-window (validator / index) | verdict |
|---|---|---|---|---|---|---|---|---|
| `V1_A` | 358 | 358 / 358 | **0** | 0 / 0 | 47608 / 47608 | 47608 / 47608 | 1.8226 / 1.8226 mm | **PASS** |
| `V1_B` | 462 | 462 / 462 | **0** | 0 / 0 | 55846 / 55846 | 55846 / 55846 | 1.8258 / 1.8258 mm | **PASS** |
| `V1_C` | 367 | 367 / 367 | **0** | 0 / 0 | 41530 / 41530 | 41530 / 41530 | 1.4197 / 1.4197 mm | **PASS** |
| `V1_D` | 423 | 423 / 423 | **0** | 0 / 0 | 43951 / 43951 | 43951 / 43951 | 1.8258 / 1.8258 mm | **PASS** |
| `V2_A` | 411 | 411 / 411 | **0** | 0 / 0 | 38185 / 38185 | 38185 / 38185 | 1.8258 / 1.8258 mm | **PASS** |
| `V2_B` | 386 | 386 / 386 | **0** | 0 / 0 | 38373 / 38373 | 38373 / 38373 | 1.8291 / 1.8291 mm | **PASS** |
| `V2_C` | 417 | 417 / 417 | **0** | 0 / 0 | 37163 / 37163 | 37163 / 37163 | 1.8258 / 1.8258 mm | **PASS** |
| `V2_D` | 427 | 427 / 427 | **0** | 0 / 0 | 34592 / 34592 | 34592 / 34592 | 1.3268 / 1.3285 mm | **PASS** |

**Primary totals: 3251 routed routes audited, 0 invalid route pairs, 0 crosscheck mismatches, all verdicts PASS.**

## 2. Extension-budget D arm (frozen)

| experiment | routed | strict pass (validator / router index) | crosscheck mismatched pairs | invalid pairs (validator / index) | crossing count (validator vs index) | window count (validator vs index) | max half-window (validator / index) | verdict |
|---|---|---|---|---|---|---|---|---|
| `extended/V1_D` | 429 | 429 / 429 | **0** | 0 / 0 | 44205 / 44205 | 44205 / 44205 | 1.6590 / 1.6590 mm | **PASS** |
| `extended/V2_D` | 427 | 427 / 427 | **0** | 0 / 0 | 35287 / 35287 | 35287 / 35287 | 1.3268 / 1.3285 mm | **PASS** |

Both extension runs are strictly clean too: the extra evaluation budget adds +6 routed connections versus the primary V1_D run (429 vs 423) while V2_D reaches the same 427 routed connections with a different D-budget regime; 0 invalid pairs and 0 mismatches in both.

## 3. Independent re-audit agreement with Lead `audit_strict.json`

**ALL MATCH** for all 10 run dirs on 22 compared fields (`passed`, `routed_count`, `d56_passed_count`, `crossing_count`, `crossing_pair_count`, `spacing_violation_pairs`, `overlap_pairs`, `touch_pairs`, `crossing_window_overlap_pairs`, `double_cross_pairs`, `crossing_window_excessive_pairs`, `crossing_window_count/max_mm/mean_mm/total_length_mean_mm`, `violation_pair_count`, `small_angle_crossing_count`, `min_non_crossing_centerline_mm`, ...). Machine-readable: `per_experiment_audit_agreement.json`.

Every primary and extension run passes strict with **0 violations** of every kind: `spacing_violation_pairs=0`, `overlap_pairs=0`, `touch_pairs=0`, `crossing_window_overlap_pairs=0`, `double_cross_pairs=0`, `crossing_window_excessive_pairs=0`, `violation_pair_count=0`; `d56_passed_count == routed_count` in every run (all routed primitives are legal D56).

## 4. Historical D56 deliverable untouched

`outputs/four_side_1024_d56_optimized/routes.json` remains **byte-identical** (SHA256 `ce96833a41f21f0515008c179f0c4cc50ca53ba069dc4cb85c0d27ce0a94a5c1`), its mtime matches the recorded baseline exactly, and all 17 files under `outputs/four_side_1024_d56_optimized/` predate the start of Phase 2 (max file mtime 2026-10-19T07:56:06Z) — the historical 467-route delivery was only read, never modified. Evidence: `per_experiment_historical_untouched.json`.

## 5. Notes

- `strict pass` counts routes not involved in any invalid route pair; for all 10 frozen runs it equals the routed count because there are no invalid pairs.
- Crossing counts are counted over valid route pairs and are identical on both sides for every run; they include grouped coincident crossings exactly once. Window counts are one per grouped crossing point (all clean runs: windows == crossings).
- Max half-window is the largest exempt half width `h* + 2*sagitta`; it stays within 1.33–1.83 mm on every run, far below the 4.0 mm `crossing_window_excessive` cap, i.e. every exemption is a small local crossing region.
- **Note on the tiny max-half difference on `V2_D` / `extended/V2_D`** (1.3268 vs 1.3285 mm, Δ=1.7e-3 mm; all other runs agree to ≤3.4e-8 mm): the extreme crossing there leaves the band through a segment running exactly parallel to the partner primitive at the 0.175 mm channel pitch, so the distance-vs-arclength function has a flat plateau at exactly 0.175 mm. Both independent solvers legitimately pick slightly different points of the first target crossing (`lim = 0.1749999 mm`); the router's false-position iteration converges later on this plateau. This **never changes a verdict**: outside the window the separation is exactly 0.175 mm ≥ `lim`, and both implementations report 0 invalid pairs and 0 mismatches. Recorded in `per_experiment_crosscheck.json` under `max_half_difference`.
- Crosscheck runtime 2–10 s per experiment; commands and per-run JSONs are listed below.

## 6. Files

- `V1_A`: `comparison/crosscheck_V1_A.json`
- `V1_B`: `comparison/crosscheck_V1_B.json`
- `V1_C`: `comparison/crosscheck_V1_C.json`
- `V1_D`: `comparison/crosscheck_V1_D.json`
- `V2_A`: `comparison/crosscheck_V2_A.json`
- `V2_B`: `comparison/crosscheck_V2_B.json`
- `V2_C`: `comparison/crosscheck_V2_C.json`
- `V2_D`: `comparison/crosscheck_V2_D.json`
- `extended/V1_D`: `comparison/crosscheck_extended_V1_D.json`
- `extended/V2_D`: `comparison/crosscheck_extended_V2_D.json`
- `comparison/per_experiment_crosscheck.json` (machine-readable companion of this table)
- `comparison/per_experiment_validator_audits.json` (validator independent strict re-audits)
- `comparison/per_experiment_audit_agreement.json` (field-by-field Lead-audit agreement)
- `comparison/per_experiment_historical_untouched.json` (historical delivery evidence)
