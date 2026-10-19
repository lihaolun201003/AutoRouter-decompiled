# V3-Huang dual-height strict audit summary (authoritative)

Generated 2026-10-19T13:20:07Z by `four_side_1024.v3.validate_v3` (independent re-derivation; no router
code imported) for `four_side_1024/v3/SPEC.md` with the unchanged `strict` crossing policy
of `four_side_1024/abcd/SPEC.md` §2.1 at **clearance 0.080 mm** (lim = 0.0799999, exact local
crossing windows, 5° minimum crossing angle, 4.0 mm max half-window), fixed **R = 40 mm**,
and the V3 same/opposite/adjacent topology (relation from the CSV column, plane from the CSV row).

**Scope: 8 frozen plane runs (A/B/C/D × z1/z2) = 4096 plane identities; 1823 routed; all 8 PASS with 0 violations of every kind; crosscheck router-vs-validator mismatch = 0 over 160367 compared route pairs.**

## 1. Per-plane strict audit (authoritative)

| plane | routed/512 | routed by relation (same / opposite / adjacent) | d56_passed | crossings | <10° | window max (mm) | window mean (mm) | pair violations | single-route violations | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| `A_z1` | 236 | 37 / 180 / 19 | 236 | 25248 | 422 | 1.073627 | 0.114008 | 0 | 0 | **PASS** |
| `A_z2` | 219 | 37 / 166 / 16 | 219 | 22955 | 344 | 0.911719 | 0.112892 | 0 | 0 | **PASS** |
| `B_z1` | 240 | 101 / 115 / 24 | 240 | 34977 | 608 | 1.083271 | 0.120848 | 0 | 0 | **PASS** |
| `B_z2` | 233 | 102 / 106 / 25 | 233 | 34029 | 563 | 1.366808 | 0.120717 | 0 | 0 | **PASS** |
| `C_z1` | 247 | 63 / 147 / 37 | 247 | 34144 | 559 | 1.052858 | 0.118085 | 0 | 0 | **PASS** |
| `C_z2` | 218 | 60 / 129 / 29 | 218 | 28811 | 429 | 1.073627 | 0.117216 | 0 | 0 | **PASS** |
| `D_z1` | 221 | 70 / 133 / 18 | 221 | 24712 | 438 | 1.062292 | 0.119146 | 0 | 0 | **PASS** |
| `D_z2` | 209 | 78 / 119 / 12 | 209 | 23720 | 423 | 1.049657 | 0.119802 | 0 | 0 | **PASS** |
| **TOTAL (8 planes)** | **1823** | **548 / 1095 / 180** | **1823** | **228596** | **3786** | **1.366808** | — | 0 | 0 | **8/8 PASS** |

All violation counters are zero in every plane: `spacing_violation_pairs`, `overlap_pairs`,
`touch_pairs`, `double_cross_pairs`, `crossing_window_overlap_pairs`,
`crossing_window_excessive_pairs`, `violation_pair_count`, `self_intersections`,
`self_overlaps`, `self_spacing_violations`, `radius_violations`, `boundary_violations`,
`diagonal_line_violations`, `free_or_short_s_arc_violations`. `d56_passed == routed` for all
8 planes; the crossing-angle histogram sums equal `crossing_count` for every plane.

## 2. V3 topology contract (relation from the CSV column)

| class | planned identities (8 planes) | observed identities | routed | routed rate |
|---|---|---|---|---|
| same | 1792 | 1792 | 548 | 30.58% |
| opposite | 1536 | 1536 | 1095 | 71.29% |
| adjacent | 768 | 768 | 180 | 23.44% |
| **total** | **4096** | **4096** | **1823** | 44.51% |

Per-plane identity counts independently re-parsed from the frozen CSV: z1 same 222 / opposite
196 / adjacent 94; z2 same 226 / opposite 188 / adjacent 98 (overall 448 / 384 / 192).
Relation is always taken from the CSV `relation` column (never inferred from the row number);
plane is CSV row 1 → z1, row 2 → z2. Contract match: **True**.

## 3. Failure taxonomy — failed identities are not violations

Failed identities are connections for which the router found no legal fixed-R=40 candidate under the frozen strict policy.  They are reported as failed (not routed) and are NOT violations of the accepted geometry: the independent audit of the routed primitives finds zero violations. Same-side U/hairpin loops often fail with double_cross/spacing/tangent_touch at the strict-policy geometric limit -- a real geometric result.

- failed identities: `no_candidate_generated` = 132, `no_legal_candidate` = 2141 (total 2273 of 4096)
- router candidate-level rejection counts during search (candidate evaluations rejected
  before acceptance; these are NOT violations of the accepted geometry): `double_cross` = 94290, `overlap` = 4547, `spacing` = 69656, `tangent_touch` = 24158.
- The authoritative audit covers only the routed primitives and finds 0 violations, so the
  accepted V3 geometry is strictly legal; same-side U/hairpin failures at the strict
  `double_cross`/`spacing` limits are real geometric results of the frozen policy.

## 4. Router-vs-validator crosscheck (`crosscheck_v3.py`)

| plane | pairs compared | mismatch | invalid pairs (validator/router) | crossings (validator/router) | windows (validator/router) | max half (validator/router, mm) | verdict |
|---|---|---|---|---|---|---|---|
| `A_z1` | 20848 | 0 | 0 / 0 | 25248 / 25248 | 25248 / 25248 | 1.073627 / 1.073627 | **PASS** |
| `A_z2` | 18689 | 0 | 0 / 0 | 22955 / 22955 | 22955 / 22955 | 0.911719 / 0.911716 | **PASS** |
| `B_z1` | 22567 | 0 | 0 / 0 | 34977 / 34977 | 34977 / 34977 | 1.083271 / 1.083271 | **PASS** |
| `B_z2` | 21376 | 0 | 0 / 0 | 34029 / 34029 | 34029 / 34029 | 1.366808 / 1.366809 | **PASS** |
| `C_z1` | 23677 | 0 | 0 / 0 | 34144 / 34144 | 34144 / 34144 | 1.052858 / 1.052852 | **PASS** |
| `C_z2` | 18816 | 0 | 0 / 0 | 28811 / 28811 | 28811 / 28811 | 1.073627 / 1.073627 | **PASS** |
| `D_z1` | 18020 | 0 | 0 / 0 | 24712 / 24712 | 24712 / 24712 | 1.062292 / 1.062292 | **PASS** |
| `D_z2` | 16374 | 0 | 0 / 0 | 23720 / 23720 | 23720 / 23720 | 1.049657 / 1.049657 | **PASS** |

**Crosscheck total: 160367 route pairs compared, mismatch = 0, invalid pairs 0/0 on both sides, crossing counts and crossing-window counts identical for every plane.**

## 5. Verification / guard rails

- 8/8 plane audits PASS; total violations across all planes: **0**.
- `d56_passed == routed` in all planes (1823 / 1823).
- Max half-window observed: **1.366808 mm** (all planes far below the 4.0 mm `crossing_window_excessive` cap; 0 excessive windows).
- Crosscheck mismatch total: **0** over 160367 pairs; no plane has mismatch > 0; validator-side max half-window equals the per-plane audit value.
- Process parameters confirmed from each `routes.json` `process` block: R = 40.0 mm fixed,
  width 0.050 mm, gap 0.030 mm, clearance 0.080 mm, lim 0.0799999, layer 0 (z is plane metadata).
- Each plane is one independent 2D problem; cross-plane XY projections are not conflicts.

## 6. Files

- `comparison/strict_audit_summary.json` (machine-readable companion of this file)
- per-plane `audit_strict.json` next to each `planes/<A|B|C|D>/<z1|z2>/routes.json`
- `comparison/crosscheck_planes__<ALGO>__<z1|z2>.json` for all 8 planes; `comparison/crosscheck_summary.json`
- validator: `four_side_1024/v3/validate_v3.py`; crosscheck: `four_side_1024/v3/crosscheck_v3.py`
