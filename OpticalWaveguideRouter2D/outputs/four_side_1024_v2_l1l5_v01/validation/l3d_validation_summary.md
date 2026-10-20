# 独立三维验收报告 — corrected L1–L5 physical layer model (R9)

Generated: 2026-10-20T15:26:15Z · validator `four_side_1024.l3d.validate_l3d` · root `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\outputs\four_side_1024_v2_l1l5_v01`

## Verdict

- **Formal acceptance: REFUSED for every payload** — L2–L5 physical heights are `unconfirmed_simulation` parameters (SCHEMA_L3D.md §1); only exploratory geometry verdicts are reported.
- **Exploratory verdict: PASS on all 8/8 validated artefacts** — `exploratory_pass=true`, all 8 violation counters 0, min curvature 14.999999961 mm ≥ 14.985 mm, min 3D clearance 0.080000000 mm ≥ 0.08 mm.
- 2 baselines (fixed L1 flats) + 6 scheme/stack finals (stage-4 relayered) validated independently from the JSON.

## Per-artefact results

| artefact | routed/failed | lifted | transitions 0/2/3/≥4 | ≥3-trans routes | min curvature (mm) | min 3D clearance (mm) | same-plane crossings per physical plane | violations | status |
|---|---|---|---|---|---|---|---|---|---|
| `baseline/schemeA` | 943/81 | 0 | 943/0/0/0 | 0 | 14.999999961 | 0.080295032 | L1 row z1 @z=0.0: 69072, L1 row z2 @z=0.5: 67110 | 0 | exploratory_only (formal=False) |
| `baseline/schemeB` | 515/509 | 0 | 515/0/0/0 | 0 | 14.999999961 | 0.080000000 | L1 row z1 @z=0.0: 13342, L1 row z2 @z=0.5: 40842 | 0 | exploratory_only (formal=False) |
| `l3d/schemeA/layers5_medium_050` | 963/61 | 44 | 919/20/19/5 | 24 | 14.999999961 | 0.080295032 | L1 row z1 @z=0.0: 69072, L1 row z2 @z=0.5: 62111, L2 @z=1.0: 221, L3 @z=1.5: 56, L4 @z=2.0: 0, L5 @z=2.5: 6 | 0 | exploratory_only (formal=False) |
| `l3d/schemeA/layers5_compact_025` | 962/62 | 43 | 919/19/19/5 | 24 | 14.999999961 | 0.080295032 | L1 row z1 @z=0.0: 69072, L1 row z2 @z=0.5: 61494, L2 @z=0.75: 230, L3 @z=1.0: 83, L4 @z=1.25: 0, L5 @z=1.5: 6 | 0 | exploratory_only (formal=False) |
| `l3d/schemeA/layers5_wide_100` | 963/61 | 44 | 919/20/19/5 | 24 | 14.999999961 | 0.080295032 | L1 row z1 @z=0.0: 69072, L1 row z2 @z=0.5: 63267, L2 @z=1.5: 120, L3 @z=2.5: 82, L4 @z=3.5: 4, L5 @z=4.5: 2 | 0 | exploratory_only (formal=False) |
| `l3d/schemeB/layers5_medium_050` | 621/403 | 130 | 491/99/24/7 | 31 | 14.999999961 | 0.080000000 | L1 row z1 @z=0.0: 13864, L1 row z2 @z=0.5: 39988, L2 @z=1.0: 518, L3 @z=1.5: 296, L4 @z=2.0: 811, L5 @z=2.5: 354 | 0 | exploratory_only (formal=False) |
| `l3d/schemeB/layers5_compact_025` | 611/413 | 120 | 491/96/20/4 | 24 | 14.999999961 | 0.080000000 | L1 row z1 @z=0.0: 13350, L1 row z2 @z=0.5: 38207, L2 @z=0.75: 1996, L3 @z=1.0: 206, L4 @z=1.25: 212, L5 @z=1.5: 166 | 0 | exploratory_only (formal=False) |
| `l3d/schemeB/layers5_wide_100` | 611/413 | 120 | 491/96/23/1 | 24 | 14.999999961 | 0.080000000 | L1 row z1 @z=0.0: 13402, L1 row z2 @z=0.5: 38324, L2 @z=1.5: 342, L3 @z=2.5: 1579, L4 @z=3.5: 210, L5 @z=4.5: 52 | 0 | exploratory_only (formal=False) |


Note on the re-layered routes: every stack was re-layered by the stage-4 relayer (24 routes per stack, `relayer.reported_relayered=24`); a payload's own transition histogram may exceed 24 only where earlier stages had already produced multi-transition routes.
- `l3d/schemeB/layers5_medium_050`: stage-4 relayer re-layered 24 routes, but the payload also contains 7 pre-existing routes with >=3 transitions from the full stage, so the payload total is 31 routes with >=3 transitions.

## 10 required checks (SCHEMA_L3D.md §4)

1. **PASS** (8/8) — L1 is the interface layer and contains BOTH port rows (z1=0.0 mm, z2=0.5 mm)
2. **PASS** (8/8) — Two same-column ports of the two rows keep their 0.5 mm real 3D distance
3. **PASS** (8/8) — Every route starts/ends exactly on a correct L1 port with the correct row z
4. **PASS** (8/8) — Transitions L1->L2..L5 are legal (R=15, theta/footprint/length from dz, endpoints and horizontal tangent continuity)
5. **PASS** (8/8) — Intermediate-layer / multiple / multi-layer transitions are legal and every layer pair is allowed by the symmetric allowed_transitions graph
6. **PASS** (8/8) — Full 3D curvature: path sampled at <=0.02 mm, min circumradius >= 14.985 mm; flat arcs exactly R=15, lines axis-aligned, transitions analytic R=15
7. **PASS** (8/8) — Transitions / other-layer parts vs L1 row flats: true 3D distance >= 0.08 mm (no crossing exemption across different physical z)
8. **PASS** (8/8) — Same logical layer but different physical height is checked in real 3D; same physical z planar pairs use the frozen strict 2D rules (legal crossings only)
9. **PASS** (8/8) — layer_id is never used as a z coordinate (same layer_id with different z -> distinct planes; different layer_ids at close z -> still checked/rejected)
10. **PASS** (8/8) — Unconfirmed / invalid L2-L5 heights refuse formal acceptance (status=exploratory_only, formal_acceptance=false)

## Aggregates

- routed: 6189, failed: 2003, lifted: 501, transitions: 1180 (≥3-transition routes: 151; 144 routes re-layered by the stage-4 relayer)
- min curvature radius: 14.999999961 mm (limit 14.985 mm)
- min 3D clearance: 0.080000000 mm (limit 0.08 mm); min transition-vs-flat: 0.091539620 mm; min transition-vs-transition: 0.081737754 mm
- same-plane crossings (legal strict 2D windows): 749141 total; all per-plane violation counts 0
- formal acceptance granted anywhere: **False** (all payloads are `unconfirmed_simulation`; status `exploratory_only`, exit 0 only with `--allow-exploratory`)
- all layer stacks valid: **True**; all provenances unconfirmed: **True**; all exit codes 0 with --allow-exploratory: **True**

Per-artefact JSON reports: `<artefact>/validation/routes_l3d.validation.json`.
