# FSLW R=40 mm / 0.080 mm-clearance strict audit summary (authoritative)

Generated 2026-10-19T11:05:09Z by `four_side_1024.fslw.validate_fslw` (independent re-derivation: no router
index / d56 validator imported) for `four_side_1024/fslw/SPEC.md` §4 = `four_side_1024/abcd/SPEC.md` §2.1 with clearance 0.080 mm (lim = clearance − 1e-7,
h*+2·sagitta local windows, 5° minimum crossing angle, 4.0 mm max half window).

**Scope: 16 frozen height-plane runs + 8 Phase-11 sensitivity runs = 24 audits; all PASS, 0 violations of every kind, crosscheck router-vs-validator mismatch = 0 over 918942 compared route pairs.**

> **Failed identities are not violations.** A failed identity is a connection for which the
> router generated no legal fixed-R=40 candidate (`no_candidate_generated` /
> `no_legal_candidate`); it is a geometric feasibility limit, is reported as failed and is
> **not** an illegal/rejected geometry. Only routed primitives are geometrically audited.
> Overall failed identities: `no_legal_candidate` = 3729, `no_candidate_generated` = 954 (total 4683 of 12288 plane identities).
>
> Plane z1 (CSV row 1, opposite) and plane z2 (CSV row 2, adjacent) are independent 2D
> problems; XY-projected cross-plane crossings are not same-layer conflicts and are never
> counted as violations. Plane height z is metadata; primitives are pure 2D layer 0.

## 1. Primary matrix — 16 plane runs (V1/V2 x A/B/C/D x z1/z2)

| plane | routed/512 | d56_passed | crossings | histogram ok | <10° | window max (mm) | window mean (mm) | spacing | overlap | touch | win overlap | double cross | excessive | single-route viol. | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `V1_A_z1` | 367 | 367 | 47061 | ✓ | 575 | 1.302720 | 0.110635 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **PASS** |
| `V1_A_z2` | 208 | 208 | 14355 | ✓ | 334 | 1.556800 | 0.127010 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **PASS** |
| `V1_B_z1` | 367 | 367 | 47061 | ✓ | 575 | 1.302720 | 0.110635 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **PASS** |
| `V1_B_z2` | 186 | 186 | 14956 | ✓ | 299 | 1.574836 | 0.120158 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **PASS** |
| `V1_C_z1` | 369 | 369 | 48051 | ✓ | 579 | 1.044151 | 0.108622 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **PASS** |
| `V1_C_z2` | 174 | 174 | 11757 | ✓ | 255 | 1.556800 | 0.127977 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **PASS** |
| `V1_D_z1` | 341 | 341 | 41360 | ✓ | 456 | 1.011245 | 0.106157 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **PASS** |
| `V1_D_z2` | 186 | 186 | 14845 | ✓ | 263 | 1.027286 | 0.116483 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **PASS** |
| `V2_A_z1` | 491 | 491 | 66664 | ✓ | 859 | 0.905816 | 0.098908 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **PASS** |
| `V2_A_z2` | 190 | 190 | 10477 | ✓ | 343 | 1.073627 | 0.136134 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **PASS** |
| `V2_B_z1` | 491 | 491 | 66664 | ✓ | 859 | 0.905816 | 0.098908 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **PASS** |
| `V2_B_z2` | 186 | 186 | 10146 | ✓ | 352 | 1.445430 | 0.137868 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **PASS** |
| `V2_C_z1` | 488 | 488 | 66018 | ✓ | 865 | 0.896366 | 0.098885 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **PASS** |
| `V2_C_z2` | 206 | 206 | 7020 | ✓ | 334 | 1.027286 | 0.159487 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **PASS** |
| `V2_D_z1` | 492 | 492 | 66775 | ✓ | 805 | 0.913783 | 0.098067 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **PASS** |
| `V2_D_z2` | 146 | 146 | 6443 | ✓ | 223 | 0.900086 | 0.136591 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **PASS** |
| **TOTAL (16 planes)** | **4888** | **4888** | **539653** | ✓ | **7976** | **1.574836** | — | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **16/16 PASS** |

`routed` = routed identities of 512; `d56_passed` = routed routes whose primitives are
legal D56 R=40 geometry (`d56_passed == routed` for every run). `window max/mean` are the
largest / mean exempt half width h*+2·sagitta. `single-route viol.` = self-intersection +
self-overlap + self-spacing + radius + boundary + diagonal-line + free-arc violations.

Combined layouts (z1+z2 routed, matching the final generator matrix):

| layout | routed (z1+z2) | expected | match |
|---|---|---|---|
| V1_A | 575 | 575 | ✓ |
| V1_B | 553 | 553 | ✓ |
| V1_C | 543 | 543 | ✓ |
| V1_D | 527 | 527 | ✓ |
| V2_A | 681 | 681 | ✓ |
| V2_B | 677 | 677 | ✓ |
| V2_C | 694 | 694 | ✓ |
| V2_D | 638 | 638 | ✓ |

## 2. Phase-11 sensitivity arm — 8 plane runs (V1+B x z1/z2 x 4 configs)

| run | R (mm) | gap (mm) | clearance (mm) | routed/512 | d56_passed | crossings | <10° | window max (mm) | window mean (mm) | violations | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `G_gap30_R5_V1_B_z1` | 5.0 | 0.030 | 0.080 | 423 | 423 | 76203 | 10 | 0.793792 | 0.089118 | 0 | **PASS** |
| `G_gap30_R5_V1_B_z2` | 5.0 | 0.030 | 0.080 | 512 | 512 | 65280 | 0 | 0.281239 | 0.088019 | 0 | **PASS** |
| `N_R40_gap30_V1_B_z1` | 40.0 | 0.030 | 0.080 | 367 | 367 | 47061 | 575 | 1.302720 | 0.110635 | 0 | **PASS** |
| `N_R40_gap30_V1_B_z2` | 40.0 | 0.030 | 0.080 | 186 | 186 | 14956 | 299 | 1.574836 | 0.120158 | 0 | **PASS** |
| `O_legacy_R5_gap125_V1_B_z1` | 5.0 | 0.125 | 0.175 | 266 | 266 | 22949 | 5 | 1.542396 | 0.199470 | 0 | **PASS** |
| `O_legacy_R5_gap125_V1_B_z2` | 5.0 | 0.125 | 0.175 | 480 | 480 | 56842 | 2 | 1.799704 | 0.192439 | 0 | **PASS** |
| `R_R40_gap125_V1_B_z1` | 40.0 | 0.125 | 0.175 | 306 | 306 | 31101 | 455 | 3.446992 | 0.244883 | 0 | **PASS** |
| `R_R40_gap125_V1_B_z2` | 40.0 | 0.125 | 0.175 | 177 | 177 | 12975 | 242 | 2.537132 | 0.261974 | 0 | **PASS** |
| **TOTAL (8 runs)** | — | — | — | **2717** | **2717** | **327367** | **1588** | **3.446992** | — | 0 | **8/8 PASS** |

Process parameters were resolved independently from each run's `routes.json` `process`
block (validated against the SPEC §7 matrix O=5/0.125, G=5/0.030, R=40/0.125,
N=40/0.030; clearance = width + gap).

## 3. Violation counters — totals

| counter | planes (16) | sensitivity (8) | all 24 |
|---|---|---|---|
| spacing | 0 | 0 | 0 |
| overlap | 0 | 0 | 0 |
| touch | 0 | 0 | 0 |
| crossing_window_overlap | 0 | 0 | 0 |
| double_cross | 0 | 0 | 0 |
| crossing_window_excessive | 0 | 0 | 0 |
| violation_pairs | 0 | 0 | 0 |
| self_intersections | 0 | 0 | 0 |
| self_overlaps | 0 | 0 | 0 |
| self_spacing | 0 | 0 | 0 |
| radius | 0 | 0 | 0 |
| boundary | 0 | 0 | 0 |
| diagonal_line | 0 | 0 | 0 |
| free_or_short_s_arc | 0 | 0 | 0 |
| **total** | **0** | **0** | **0** |

## 4. Router-vs-validator crosscheck (`fslw/crosscheck_fslw.py`)

Each broad-phase route pair is isolated in the router index (`D56Index(width, gap, crossing_policy='strict')`, width/gap from the
run's process block) and in the independent validator; the boolean verdicts, crossing counts and
crossing-window counts must agree (`mismatch = 0`). The validator is authoritative.

| run | pairs compared | mismatch | invalid pairs (validator/router) | crossings (validator/router) | windows (validator/router) | max half (validator/router, mm) | verdict |
|---|---|---|---|---|---|---|---|
| `V1_A_z1` | 50284 | 0 | 0 / 0 | 47061 / 47061 | 47061 / 47061 | 1.302720 / 1.302720 | **PASS** |
| `V1_A_z2` | 17315 | 0 | 0 / 0 | 14355 / 14355 | 14355 / 14355 | 1.556800 / 1.556800 | **PASS** |
| `V1_B_z1` | 50284 | 0 | 0 / 0 | 47061 / 47061 | 47061 / 47061 | 1.302720 / 1.302720 | **PASS** |
| `V1_B_z2` | 15281 | 0 | 0 / 0 | 14956 / 14956 | 14956 / 14956 | 1.574836 / 1.574833 | **PASS** |
| `V1_C_z1` | 51184 | 0 | 0 / 0 | 48051 / 48051 | 48051 / 48051 | 1.044151 / 1.044149 | **PASS** |
| `V1_C_z2` | 11672 | 0 | 0 / 0 | 11757 / 11757 | 11757 / 11757 | 1.556800 / 1.556800 | **PASS** |
| `V1_D_z1` | 42231 | 0 | 0 / 0 | 41360 / 41360 | 41360 / 41360 | 1.011245 / 1.011245 | **PASS** |
| `V1_D_z2` | 15137 | 0 | 0 / 0 | 14845 / 14845 | 14845 / 14845 | 1.027286 / 1.027286 | **PASS** |
| `V2_A_z1` | 67196 | 0 | 0 / 0 | 66664 / 66664 | 66664 / 66664 | 0.905816 / 0.905814 | **PASS** |
| `V2_A_z2` | 15490 | 0 | 0 / 0 | 10477 / 10477 | 10477 / 10477 | 1.073627 / 1.073627 | **PASS** |
| `V2_B_z1` | 67196 | 0 | 0 / 0 | 66664 / 66664 | 66664 / 66664 | 0.905816 / 0.905814 | **PASS** |
| `V2_B_z2` | 15161 | 0 | 0 / 0 | 10146 / 10146 | 10146 / 10146 | 1.445430 / 1.445429 | **PASS** |
| `V2_C_z1` | 66562 | 0 | 0 / 0 | 66018 / 66018 | 66018 / 66018 | 0.896366 / 0.896364 | **PASS** |
| `V2_C_z2` | 11144 | 0 | 0 / 0 | 7020 / 7020 | 7020 / 7020 | 1.027286 / 1.027286 | **PASS** |
| `V2_D_z1` | 67418 | 0 | 0 / 0 | 66775 / 66775 | 66775 / 66775 | 0.913783 / 0.913783 | **PASS** |
| `V2_D_z2` | 9564 | 0 | 0 / 0 | 6443 / 6443 | 6443 / 6443 | 0.900086 / 0.900084 | **PASS** |
| `G_gap30_R5_V1_B_z1` | 72106 | 0 | 0 / 0 | 76203 / 76203 | 76203 / 76203 | 0.793792 / 0.793783 | **PASS** |
| `G_gap30_R5_V1_B_z2` | 73664 | 0 | 0 / 0 | 65280 / 65280 | 65280 / 65280 | 0.281239 / 0.281239 | **PASS** |
| `N_R40_gap30_V1_B_z1` | 50284 | 0 | 0 / 0 | 47061 / 47061 | 47061 / 47061 | 1.302720 / 1.302720 | **PASS** |
| `N_R40_gap30_V1_B_z2` | 15281 | 0 | 0 / 0 | 14956 / 14956 | 14956 / 14956 | 1.574836 / 1.574833 | **PASS** |
| `O_legacy_R5_gap125_V1_B_z1` | 22863 | 0 | 0 / 0 | 22949 / 22949 | 22949 / 22949 | 1.542396 / 1.542396 | **PASS** |
| `O_legacy_R5_gap125_V1_B_z2` | 64662 | 0 | 0 / 0 | 56842 / 56842 | 56842 / 56842 | 1.799704 / 1.799704 | **PASS** |
| `R_R40_gap125_V1_B_z1` | 33647 | 0 | 0 / 0 | 31101 / 31101 | 31101 / 31101 | 3.446992 / 3.446991 | **PASS** |
| `R_R40_gap125_V1_B_z2` | 13316 | 0 | 0 / 0 | 12975 / 12975 | 12975 / 12975 | 2.537132 / 2.537132 | **PASS** |

**Crosscheck total: 918942 route pairs compared, mismatch = 0, per-pair crossing-count mismatches = 0, invalid pairs 0/0 on both sides for every run.**

For all 24 runs the crosscheck's validator-side maximum half-window equals the
authoritative per-run `audit_strict.json` value to <1e-6 mm, and the router-side
maximum agrees to <1e-4 mm — the two independent implementations solve the same
local windows.

## 5. Verification / guard rails

- Final generator routed matrix reproduced exactly by the independent audit (16/16 planes + 8/8 combined layouts): **True**.
- Sensitivity process parameters (R/gap/clearance from each `routes.json` `process`) match SPEC §7 for all 8 runs: **True**.
- `d56_passed == routed` and `crossing_angle_histogram` sums equal `crossing_count` for every one of the 24 runs; `violation_pair_count == 0` everywhere.
- Router-vs-validator crosscheck: 24/24 runs PASS, 918942 route pairs compared, **mismatch = 0**, per-pair crossing-count mismatches 0, invalid pairs 0/0 on both sides; validator-side max half-window equals the per-run audit value for all 24 runs.
- **Max half-window observed:** planes 1.574836 mm, sensitivity 3.446992 mm, overall **3.446992 mm** (all < 4.0 mm `crossing_window_excessive` cap; 0 excessive windows anywhere).
- Minimum non-crossing centreline distance per run ≥ clearance limit (no outside-window spacing violation anywhere).
- Previous rounds untouched: 10/10 `outputs/four_side_1024_v1_v2_abcd/<run>/routes.json` byte-identical (SHA256) and every one of the 244 files predates this round; historical `outputs/four_side_1024_d56_optimized/routes.json` still SHA256 `ce96833a41f21f0515008c179f0c4cc50ca53ba069dc4cb85c0d27ce0a94a5c1` (17 files, all predate this round). Guard: True. Evidence: `previous_rounds_untouched.json`.

## 6. Files

- `comparison/strict_audit_summary.json` (machine-readable companion of this file)
- per-plane `audit_strict.json` next to each run's `routes.json` (authoritative audit)
- `comparison/crosscheck_<run>.json` for all 24 runs; `comparison/crosscheck_summary.json`
- `comparison/previous_rounds_untouched.json`
- validator: `four_side_1024/fslw/validate_fslw.py`; crosscheck: `four_side_1024/fslw/crosscheck_fslw.py`
