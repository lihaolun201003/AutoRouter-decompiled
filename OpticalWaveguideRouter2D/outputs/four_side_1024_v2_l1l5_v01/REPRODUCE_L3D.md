# Corrected L1–L5 five-layer round (2026-10-20 R9): reproduce

All commands run in the project root with PowerShell:

```powershell
Set-Location "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
```

Run order matters: the R15 profile (R = 15 mm for planar bends and 3D elevation
curves) is applied inside each runner before any radius-binding module is imported.
L2–L5 heights are **exploratory, unconfirmed simulation parameters**; no command below
produces a formal process acceptance.

## 0. Corrected model in one paragraph

The old 2.5D model identified the z1 row with L1 (z=0) and the z2 row with L5
(z=0.5), compressing four extra layers into 0.125/0.25/0.375 mm between the two
interface rows. That is wrong. The corrected model puts **both interface rows on the
logical interface layer L1**: z1 row at physical z=0.0 mm and z2 row at physical
z=0.5 mm (real 0.5 mm height difference). L2–L5 are four additional routing layers
whose heights are not confirmed; this round explores three configurable stacks
(`medium_050` = 1.0/1.5/2.0/2.5 mm, `compact_025` = 0.75/1.0/1.25/1.5 mm,
`wide_100` = 1.5/2.5/3.5/4.5 mm). Logical layer id, port physical height, current
waveguide physical height and current logical layer are kept strictly separate.
Routes may visit any layer sequence (L1→L2→L3→L1, L1→L5→L3→L1, etc.), may change
layer multiple times, and must return to L1 at the true port row height.

## 1. Stage 1 — corrected L1 baseline from the accepted R15 2D layouts

The accepted R15 2D layouts A=943 (z1 498 + z2 445) and B=515 (184 + 331) are
re-interpreted as L1 flat routes at their true row heights (z1 row 0.0 mm, z2 row
0.5 mm) and re-checked in one real-XYZ world. No old 2.5D lifted route is reused.

```powershell
.\.venv\Scripts\python.exe -m four_side_1024.l3d.run_l3d --scheme A --stage baseline
.\.venv\Scripts\python.exe -m four_side_1024.l3d.run_l3d --scheme B --stage baseline
```

Output: `outputs/four_side_1024_v2_l1l5_v01/baseline/scheme{A,B}/routes_l3d.json`.

## 2. Stages 2–4 — routing on the corrected model (three exploratory stacks)

* stage 2 (single lift): each failed route may climb once to L2..L5 and return to
  its L1 row height; all layer choices are compared before accepting a candidate;
* stage 3 (multi-layer): additionally tries multi-layer sequences
  L1→Li→Lj→L1 (and deeper), including back-to-back transitions where the builder
  permits it;
* stage 4 (local re-layering / R&R): the router runs a bounded rip-up-and-reroute;
  then `postpass` re-lays already accepted flat routes over 3/4-transition
  sequences (L1→L2→L3→L1, L1→L2→L3→L5→L1, ...) without losing a route.

Primary exploratory stack `medium_050` (A and B, full stage):

```powershell
.\.venv\Scripts\python.exe -m four_side_1024.l3d.run_l3d --scheme A --stage full `
  --stack medium_050 --budget 120 --multi-budget 60 --passes 3 --rr-rounds 1 `
  --rr-targets 48 --rr-rip 2
.\.venv\Scripts\python.exe -m four_side_1024.l3d.run_l3d --scheme B --stage full `
  --stack medium_050 --budget 120 --multi-budget 60 --passes 3 --rr-rounds 1 `
  --rr-targets 48 --rr-rip 2
```

Sensitivity stacks (stage 2 baseline, same budget):

```powershell
foreach ($stack in 'compact_025','wide_100') {
  .\.venv\Scripts\python.exe -m four_side_1024.l3d.run_l3d --scheme A --stage single `
    --stack $stack --budget 120 --passes 2 --rr-rounds 0
  .\.venv\Scripts\python.exe -m four_side_1024.l3d.run_l3d --scheme B --stage single `
    --stack $stack --budget 120 --passes 2 --rr-rounds 0
}
```

Stage-4 local re-layering post-pass (writes `routes_l3d.json` as final, keeps the
router output as `routes_l3d_router.json`):

```powershell
Get-ChildItem outputs/four_side_1024_v2_l1l5_v01/l3d/scheme*/layers5_*/routes_l3d.json | ForEach-Object {
  .\.venv\Scripts\python.exe -m four_side_1024.l3d.postpass --routes $_.FullName `
    --targets 24 --max-attempts 80
}
```

## 3. Independent 3D validation (corrected model)

```powershell
Get-ChildItem outputs/four_side_1024_v2_l1l5_v01/baseline/scheme*/routes_l3d.json,
             outputs/four_side_1024_v2_l1l5_v01/l3d/scheme*/layers5_*/routes_l3d.json |
  ForEach-Object {
    .\.venv\Scripts\python.exe -m four_side_1024.l3d.validate_l3d --routes $_.FullName --allow-exploratory
  }
```

The validator is independent of the router: it rebuilds every flat sample and every
transition from the JSON parameters, samples the full 3D path by exact arc length at
≤0.02 mm, and checks:
L1 two-row interface (z=0/0.5), port identity, no row change, transitions
(L1→Lk and Li→Lj, multi/back-to-back), full 3D curvature ≥ 14.985 mm, true 3D
clearance ≥ 0.08 mm for all different-physical-z pairs (incl. transitions vs L1
flats), same-physical-plane strict 2D rules with legal crossing windows, `layer_id`
never used as z, and refusal of formal acceptance while L2–L5 heights are
`unconfirmed_simulation`.

Exit codes: 0 = exploratory geometry pass; 3 = formal acceptance refused without
`--allow-exploratory` (expected here); 1 = geometry violation; 2 = invalid stack.
Reports are written next to each payload under `validation/`.

## 4. Statistics and figures

```powershell
.\.venv\Scripts\python.exe -m four_side_1024.l3d.stats_l3d
.\.venv\Scripts\python.exe -m four_side_1024.l3d.plots_l3d
```

Outputs: `outputs/four_side_1024_v2_l1l5_v01/summary/` and
`outputs/four_side_1024_v2_l1l5_v01/{figures,comparison}/`.

## 5. Tests

```powershell
.\.venv\Scripts\python.exe -m pytest four_side_1024/l3d/tests_l3d -q
```

Covers the model/data structures, multi-transition path assembly, and the ten
independent-validation requirements (including invalid-stack refusal and
curvature/clearance violations).

## 6. Important honesty notes

* L2–L5 heights are **not** supervisor-confirmed process parameters. All runs are
  exploratory geometry studies (`unconfirmed_simulation`); the validator reports
  `formal_acceptance=false` / `status=exploratory_only`.
* The old R15 five-layer results A=985 / B=723 used the wrong `z1=L1, z2=L5` model
  and are **not comparable** process results; only the R15 2D flat layouts
  (A=943, B=515) are re-used as the L1 starting layout.
* The interface position, port coordinates, port tangents, V2 connectivity CSV and
  its SHA256 are unchanged.
* All historical R15/R40 output directories are untouched; this round writes only
  `outputs/four_side_1024_v2_l1l5_v01/`.
* No loss coefficients are invented: propagation 0.05 dB/cm is an experiment
  convention (not measured); bend, crossing and interlayer effects remain
  `unknown_uncalibrated`; no total loss conclusion is produced.
