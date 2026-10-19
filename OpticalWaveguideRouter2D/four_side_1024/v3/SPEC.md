# V3-Huang 1024-channel four-side dual-height routing SPEC (round 3)

Status: implementation contract v1 (2026-10-19).  Every module in
`four_side_1024/v3/` reads the numbers from `v3/config.py`; the historical
`fslw/` and `abcd/` packages are **not modified** (their outputs must stay valid).

## 1. Inputs (frozen, never edited)

- `data/v3_huang/fiberBoard1024_huang_four_side_connectors.xlsx`
  (connector-level Port1/Port2, 64x64 relation matrix, mapping and statistics sheets)
- `data/v3_huang/fiberBoard1024_huang_fiber_pairs.csv`
  (the **routing input**: 1024 fibre-level connections with fixed endpoints)
- `data/v3_huang/PROVENANCE.json`: original Desktop paths + SHA256 of both files.
- The CSV identity/order/endpoints are never changed.  The Excel file is used only
  for cross-checking the connector topology and analysing connection patterns.

## 2. Topology (V3-Huang, from the CSV)

| class | count | composition |
|---|---:|---|
| same | 448 | NN 112, SS 112, EE 112, WW 112 |
| opposite | 384 | NS 192, EW 192 |
| adjacent | 192 | NE 48, NW 48, ES 48, SW 48 |
| total | 1024 | |

- 4 sides x 16 connectors x 32 fibres = 2048 physical ports, each used exactly once.
- Dual-height split is given by the CSV: **row 1 -> plane z1 (512 connections),
  row 2 -> plane z2 (512 connections)**.  Each plane mixes the three classes
  (z1: same 222 / opposite 196 / adjacent 94; z2: same 226 / opposite 188 / adjacent 98).
- **The relation is taken from the CSV column, never inferred from the row number.**
  Old V1/V2 assumption ("row 1 = opposite, row 2 = adjacent") is invalid here.
- Same-side connections never connect a connector to itself (validated).

## 3. Process parameters (unchanged from the FSLW round)

R = 40 mm fixed (every arc exactly 40.0), waveguide width 0.050 mm, edge gap
0.030 mm, centreline clearance 0.080 mm, propagation loss 0.05 dB/cm, board
150x150 mm, D56 primitive family only.  Bend loss and crossing loss are
`unknown_uncalibrated`; no optical totals may be fabricated.

## 4. D56 geometry families (both heights identical)

- primitives: axis-aligned lines, quarter-circle arcs (|sweep| = pi/2, R = 40),
  the historical short-S pair (`theta = acos(1 - d/(2R))`, lateral `d`, advance
  `2R sin(theta)`), and **consecutive quarter arcs without a straight in between**
  (only as a same-side 180-degree hairpin, allowed for V3 same-side families).
- No slanted lines, no free-form/Dubins arcs, no radius below 40 mm.
- Canonical frames (rigid rotation/reflection, distance preserving):
  - opposite: `p = (sx, 0)` -> `q = (tx, 150)`, start dir +y, end dir +y
  - adjacent: `p = (sx, 0)` -> `q = (150, qy)`, start dir +y, end dir +x
  - **same** (V3 new): `p = (sx, 0)` -> `q = (qx, 0)`, start dir +y, end dir **-y**
    (both ports on the same board edge; N=rot 180, S=identity, E=rot/reflection,
    W=rot/reflection, all mapping the shared edge to y = 0 with inward +y).
- The canonical frames are reused from `d56.frames` for opposite/adjacent; the
  same-side frame is added in `v3.frames` (must be a rotation/reflection of the
  square, so R and distances are invariant).

## 5. Acceptance (unchanged strict policy, clearance 0.080)

The previous round's exact local crossing-window policy is reused unchanged:
`lim = clearance - 1e-7 = 0.0799999`, exact per-crossing half-window solve,
`h* + 2*sagitta` exemption, 1e-6 crossing grouping, window overlap only across
groups, route-end clamp, `> 4 mm` = excessive, double-sided outside recheck.
Only routed geometry enters the audit; `no_candidate_generated` /
`no_legal_candidate` identities are failed-but-not-rejected, not violations.

Independent validator: `v3/validate_v3.py` (validator owner) must implement the
same rules independently (no import of the routing candidate code) and support
same-side routes (inward start tangent, outward end tangent, net 180 degrees).

## 6. Algorithms (adapted from the FSLW round, same geometry standard)

- A opposite-first: opposite -> same -> adjacent
- B same-first: same -> adjacent -> opposite (must be tested: reserving the U tracks first)
- C four-side round-robin: every side owns 256 connections containing a mix of all
  three classes; small batches interleaved by side
- D global joint (static pool + multi-start + LNS) with the extended candidate pool
- All four use the same candidate library and the same strict index; no per-algorithm
  relaxation.  Old version differences are recorded in the report.

## 7. Artifacts

```
outputs/four_side_1024_v3_huang_R40_gap30_abcd/
  inputs/          # frozen input copies + SHA256
  topology/        # connector-level demand, 64x64 matrix, validation (connectivity owner)
  planes/<A|B|C|D>/<z1|z2>/   # routes.json, failed_routes.json, config.json, run.log,
                              # CHECKPOINT.json, statistics.json, audit_strict.json,
                              # routing_all.png/svg/gds, ... (viz + validator)
  combined/<A|B|C|D>/         # routes_1024.json, statistics.json, layer_2d.png/svg,
                              # overlay_3d.png, routing_1024_two_height.gds, planes_summary.json
  shapes/          # same-side U / refold statistics and only-U figures (viz)
  feasibility/     # Phase-3 small geometry tests + same-side feasibility map (lead)
  comparison/      # all metric comparisons + strict audit summary (viz/validator)
  report/report_data.json
```

`routes.json` schema: `four_side_1024_v3_plane_routes_v1`; identical to the FSLW
plane schema but `relation` may be `same`, `pair` may be `NN/SS/EE/WW`, and the
`process`/`plane_validation` blocks report the V3 topology counts.  All 512
identities of one plane appear exactly once; every routed record carries
`primitives` (world mm), `length_mm`, `bend_count`, `propagation_loss_db`,
`candidate.family/params`; failed records carry `reason`, `evaluated`,
`rejection_counts`, `blockers`.

## 8. Honesty rules

- Never edit the input CSV/XLSX, never re-generate a replacement topology.
- Never raise the routed count by relaxing radius/gap/layer/endpoints or by
  hiding failures; report real counts and the geometric limits.
- Distinguish (A) template infeasible, (B) no implemented D56 family has a
  solution, (C) candidate exists but blocked by other routes.  No claim of
  mathematical impossibility without proof.
- The lack-of-candidate counts and failure taxonomy are reported as-is.

---

## 9. Final results (2026-10-19, implementation round 1)

All numbers below come from the eight official plane runs and their independent strict
audit; they do not change the contract above.

| plane | A | B | C | D |
|---|---:|---:|---:|---:|
| z1 routed /512 | 236 (same 37) | 240 (same 101) | 247 (same 63) | 221 (same 70) |
| z2 routed /512 | 219 (same 37) | 233 (same 102) | 218 (same 60) | 209 (same 78) |
| combined /1024 | 455 | **473** | 465 | 430 |

- 8/8 planes pass the independent strict audit: 0 violations of every kind,
  `d56_passed == routed`, crosscheck mismatch = 0 (160 367 route pairs).
- 8-plane totals: 1823/4096 routed; same 548/1792 (30.6 %), opposite 1095/1536 (71.3 %),
  adjacent 180/768 (23.4 %); 228 596 same-plane crossings; max half-window 1.366808 mm.
- Class-isolation capacity (same router, one class alone): same-side 101/222 (z1) and
  102/226 (z2); opposite 186/196 and 160/188; adjacent 63/94 and 61/98.
  Per-side same-side isolation ≈95 %; four sides together ≈45 %.
- Geometry facts learned: only 53/448 same-side pairs allow the plain U (|dx| >= 2R);
  395/448 need the short-S + 180-degree hairpin refold (loop height 40-120 mm).
  The dominant same-side failure reason is the strict policy (no double crossings) plus
  spacing between the four sides' large loops, not missing candidate families.
- Honesty: the V3 candidate library was extended for same-side connections, so V3 vs
  V1/V2/FSLW routed counts are descriptive only (see the report section 9.5).
