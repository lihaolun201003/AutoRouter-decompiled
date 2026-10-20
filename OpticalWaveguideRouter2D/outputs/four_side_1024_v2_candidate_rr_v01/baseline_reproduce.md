# V2 dual-height 698-channel BASE baseline (T1) - reproduction

Recombined 1024-channel baseline for the FSLW R=40 mm / edge-gap 0.030 mm
process: plane z1 = 492 opposite connections, plane z2 = 206 adjacent
connections, 698/1024 routed (68.1640625%).

## Provenance (read-only historical inputs, nothing modified)

| plane | source routes.json | original algorithm | routed |
|---|---|---|---|
| z1 | `outputs/four_side_1024_fslw_R40_gap30_abcd/planes/V2/D/z1/routes.json` | D | 492 |
| z2 | `outputs/four_side_1024_fslw_R40_gap30_abcd/planes/V2/C/z2/routes.json` | C | 206 |

The routed primitives/lengths/bends/candidate metadata are copied verbatim (a
JSON deep-equality check against the historical files is part of the
acceptance).  Connection identities are rebuilt as a zero-change projection of
the frozen V2 CSV through `four_side_1024.fslw.ports.load_plane('V2', plane)`.
No routing search is run and no geometry of the historical solutions is edited.

## Reproduce

Run from `OpticalWaveguideRouter2D`:

```bat
cd "C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D"
.venv\Scripts\python.exe four_side_1024\v2opt\audit_baseline.py
.venv\Scripts\python.exe -m pytest four_side_1024\v2opt\tests -q
```

The script rebuilds, idempotently:

* `planes/V2/BASE/z1/{routes.json, config.json, audit_strict.json, statistics.json}`
* `planes/V2/BASE/z2/{routes.json, config.json, audit_strict.json, statistics.json}`
* `combined/V2/BASE/` via `four_side_1024.fslw.combine.build_combined(root,'V2','BASE')`
  (`routes_1024.json`, `statistics.json`, `planes_summary.json`,
  `routing_1024_two_height.gds`, `layer_2d.png/.svg`, `overlay_3d.png`, plus the
  per-plane `routing_all.gds/.svg`)
* `baseline_acceptance.json` - all seven T1 criteria with real numbers and PASS/FAIL
* this `baseline_reproduce.md`

## Acceptance gates (all must be true)

1. 512 records per plane, identity fields identical to the frozen V2 CSV,
   CSV sha256 = 49dd9e89c4ea506d04638ae34eb06a0d8163d479de80869804c881ee1c43915e.
2. routed primitives byte-equal (JSON deep equality) to the historical files, 492/206.
3. `four_side_1024.fslw.validate_fslw` strict policy passed=True per plane
   (`audit_strict.json` includes the routes sha256).
4. `four_side_1024.fslw.metrics.build_plane_statistics` -> statistics.json with
   `audit_passed=True` merged from `audit_strict.json`.
5. `four_side_1024.fslw.combine.build_combined` -> 698 routed, routing_rate
   698/1024, dual-height GDS (layer 0 = z1, layer 1 = z2) and figures generated,
   combined audit declares 0 same-plane violations.
6. Independent recomputation: `four_side_1024.d56.index.D56Index`
   (width=0.05 mm, gap=0.03 mm, crossing_policy='strict') rebuild + per-route
   leave-one-out exclude self-check -> zero violations; `fslw.crosscheck_fslw`
   router-vs-validator pair-verdict agreement (0 mismatches).
7. Comparison of the eight historical V1/V2 x A/B/C/D groups (694/677/681/638
   for V2) against the 698 recombination.

`baseline_acceptance.json` is the machine-readable verdict; the script exits 0
only when every criterion passes.
