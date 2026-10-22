# Manual-C4 campaign — independent verification summary (phases 2–5)

Verifier: `pipeline-analyst` (read-only; no producer code imported for the verdicts).
All scripts live in this directory and write only into
`outputs/manual_c4_new_connectivity/verification/`.

| Stage | Verdict | Runtime | Report |
|---|---|---|---|
| phase2_2d | **PASS** (19/19 checks) | 6.6 s | `phase2_verification.json` / `.md` |
| phase3_initial_lift | **PASS** (13/13 checks) | 8–10 s | `phase3_verification.json` / `.md` |
| phase4_ablation A/B/C/D | **PASS** (44/44 checks) | 32 s | `phase4_verification.json` / `.md` |
| phase5_dynamic_optimization | **PASS** (28/28 checks, 2 benign warnings) | 14 s | `phase5_verification.json` / `.md` |

Scripts: `verify_phase2.py` (2D), `verify_3d.py --stage phase3|phase4|phase5`, with
`--dry` load-only self test.  The verifier re-reads the original manual CSVs, the
authoritative port model (`fslw.ports.build_plane_endpoints`) and the phase-2
records, and re-derives every number itself; only the frozen
`fslw.validate_fslw` (2D strict pair audit) and `l3d.validate_l3d` (true-3D
geometry, driven with the phase-2 identity) are reused.

## Phase 2 (2D routing) — inputs/connectivity/2D geometry

- 1024 connections (route_id 1..1024); the two manual CSVs match
  `connectivity_1024.csv` row-by-row (z2 offset +512), 0 differences;
  2048 physical ports used exactly once (z1 1024 / z2 1024); row/column/channel
  formulas all correct.
- 256 C4 quartets (z1 128 / z2 128): opposite 68, same 64, adjacent 124;
  90/180/270 rotation closure 0 missing; groups match the manifest; 768/768
  independent rotation geometry checks pass (691 forward / 77 reversed).
- 1024/1024 routed (0 failed); identity/endpoints/relation/sides/rows match the
  manifest; per-plane payloads identical to the combined `routes_1024.json`.
- frozen fslw strict: **0 violations**, z1 29376 crossing pairs (30608 points),
  z2 13208 pairs (14992 points) → **42584 unique pairs**; min non-crossing
  centreline z1 0.252049 mm / z2 0.154291 mm; total 2D length 97438.4405 mm.

## Phase 3 (initial crossing-avoidance lift, medium_050) — PASS

- 1024 routed; **47 quartets / 188 routes lifted**, **376 transitions**
  (climb+descent), high layers L2 104 / L3 32 / L4 24 / L5 28.
- same-height crossings **42584 → 25308 (−17276, −40.57 %)**; per-height pairs
  17936+7328+20+20+0+4 = 25308; 25564 points; summary / crossings_after /
  independent recomputation agree.
- every route: XYZ ports unchanged, XY projection an exact sub-chain of the
  phase-2 primitives, transitions only on single 2D straight segments, ≤1 climb
  + ≤1 descent, all arcs R=15; C4 3D 256 groups ×3 phases rigid rotations exact.
- independent l3d: **9 count classes = 0**, exploratory PASS, formal refused,
  min curvature 14.999999965 mm, min 3D clearance 0.086214914 mm, 2048 ports.
- lift_plans (47 lifted / 42 rejected / 11 reverted) consistent with routes_l3d
  (layer/footprint/rise-fall/high spans); reverted groups are flat; checkpoint
  and 58 step checkpoints consistent; repair_rounds = 5.

## Phase 4 (layer-spacing ablation A/B/C/D) — PASS

Same manifest/baseline (42584), same budget; only L2–L5 heights differ;
1024/1024 routed in every configuration, 9 count classes = 0, exploratory PASS,
formal refused, min curvature 14.999999965 mm.

| config | L2/L3/L4/L5 (mm) | remaining unique pairs | lifted groups / routes | transitions | min 3D clearance | points |
|---|---|---:|---:|---:|---:|---:|
| A_0.25mm | 0.75/1.00/1.25/1.50 | **20416** | 72 / 288 | 576 | 0.081609912 | 20800 |
| B_0.50mm | 1.00/1.50/2.00/2.50 | **25308** | 47 / 188 | 376 | 0.086214914 | 25564 |
| C_0.75mm | 1.25/2.00/2.75/3.50 | **20820** | 67 / 268 | 536 | 0.091518627 | 21248 |
| D_1.00mm | 1.50/2.50/3.50/4.50 | **21392** | 66 / 264 | 528 | 0.082167281 | 21732 |

Only the stack may differ: 1024/1024 route XY signatures are identical across
all four configurations and equal the phase-2 2D chain; the 256-quartet
partition (group_id/phase) is identical everywhere; routed/failed sets identical.
`ablation_table.json` rows match the independent recomputation for every
configuration; shared baseline verified.

## Phase 5 (dynamic layer optimisation, B input) — PASS after producer fix

- before = phase4 B (SHA identical, `input_hashes.json` matches).
- 25308 → **23356 unique pairs (−1952, −7.71 %)**; per-height pairs
  15952+7328+36+32+0+8 = 23356; 23596 points; summary / recomputation agree.
- 13 accepted actions (4 single: 1 layer change + 3 interval moves; 1 joint;
  8 failed-group retries), every action strictly decreases the unique pair count
  and `before − old + new == after`; 55 lifted groups / 220 routes / 440
  transitions; length +10.2475 mm; runtime 856 s; validation `exploratory_only`.
- after payload: 1024/1024 records now carry complete manifest identity
  (source/target endpoint, relation, pair, sides, rows) — the earlier 52-record
  metadata gap was fixed in `dynamic_opt.build_payload()` and confirmed by this
  re-run; `summary.routed_before = 1024`.
- after geometry: XY projection unchanged vs phase 2, R=15, transitions only on
  2D straight segments, ≤1 climb + ≤1 descent, C4 3D exact; independent l3d:
  9 counts = 0, exploratory PASS, formal refused, min curvature 14.999999965 mm,
  min 3D clearance 0.083207287 mm, 2048 ports.
- stage_records / checkpoint (256 groups, unique pairs 23356) / actions counts
  all consistent; before→after only layer/interval changes.

## Caveats

- L2–L5 heights remain **unconfirmed exploratory process parameters**; all 3D
  verdicts are `exploratory_only` (formal manufacturing acceptance deliberately
  refused by the repository validator).
- Crossings are a geometric metric (unique `(route_a, route_b)` pairs
  deduplicated across all physical heights); crossing optical feasibility is not
  implied.
- Warnings only: `dynamic_run` copies no `crossings_before.json` into the
  phase-5 before/after folders (the baseline lives in phase-3/4 summaries).
- The producer bugs found by this verification (phase-5 identity metadata,
  hard-coded `routed_before=1020`) are recorded in
  `outputs/manual_c4_new_connectivity/CODE_CHANGES.md` and have been fixed and
  re-verified.
