# Step 8.5-F: known propagation/bend loss and crossing angles

## 1. Existing loss.py audit
Existing APIs required no correction and were not modified.
- propagation_loss(length_cm, loss_db_per_cm=0.05): cm input, dB/cm coefficient, dB output.
- bend_loss_90(radius_mm): strict dictionary table {2:7.94, 3:6.81, 4:4.59, 5:2.39, 6:1.90} in mm/dB; unknown radius raises ValueError.
- bend_loss(radius_mm, angle_deg): L90 * angle_deg / 90; nonnegative degrees.
- total_bend_loss: sums (radius_mm, angle_deg) inputs.
- crossing_loss(angle_deg): remains NotImplementedError. It was not called by analysis.

## 2. Integration interfaces and units
src/loss_analysis.py adds analyze_route_loss_mm, crossing_angle_statistics and statistics. The route interface explicitly interprets coordinates as mm; generic models remain unit-neutral.
Exact Line lengths plus exact r*abs(sweep_rad) Arc lengths form total_length_mm. Propagation uses propagation_loss(total_length_mm/10). Every arc contributes bend loss through existing total_bend_loss, converting abs(sweep_rad) to degrees.
Measured radii are verified against configured radius_mm=5 within tol=1e-9; that configured table radius is then used. This handles construction roundoff without rounding unknown radii or inventing interpolation. Two ordinary bends are traversed, not replaced with a hard-coded 4.78.
known_non_crossing_loss_db = propagation_loss_db + bend_loss_db. General-angle bend scaling is the inherited Step 7 linear-sweep assumption, not new experimental validation.

## 3. Geometry and allocator counts
512 analytic geometries = 454 ordinary + 58 independent special-Z. Allocator remains assigned=454, unsupported_geometry=58. Special losses are analytic geometry estimates, not allocator-approved routed results.

## 4. Exact lengths and known loss statistics
All statistics below are per-route samples. Sum of dB values is an arithmetic dataset statistic across independent waveguides, NOT end-to-end system loss.

| Group | Metric | Min | Max | Mean | Median | Sum |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| ordinary | line_length_mm | 16.175000000 | 265.775000000 | 120.906167401 | 140.125000000 | 54891.400000000 |
| ordinary | arc_length_mm | 15.707963268 | 15.707963268 | 15.707963268 | 15.707963268 | 7131.415323649 |
| ordinary | total_length_mm | 31.882963268 | 281.482963268 | 136.614130669 | 155.832963268 | 62022.815323649 |
| ordinary | propagation_loss_db | 0.159414816 | 1.407414816 | 0.683070653 | 0.779164816 | 310.114076618 |
| ordinary | arc_count | 2.000000000 | 2.000000000 | 2.000000000 | 2.000000000 | 908.000000000 |
| ordinary | total_bend_angle_rad | 3.141592654 | 3.141592654 | 3.141592654 | 3.141592654 | 1426.283064730 |
| ordinary | bend_loss_db | 4.780000000 | 4.780000000 | 4.780000000 | 4.780000000 | 2170.120000000 |
| ordinary | known_non_crossing_loss_db | 4.939414816 | 6.187414816 | 5.463070653 | 5.559164816 | 2480.234076618 |
| special | line_length_mm | 140.000125001 | 144.772727767 | 142.170298313 | 142.983278900 | 8245.877302140 |
| special | arc_length_mm | 5.500469136 | 15.657963060 | 9.700293644 | 7.777416142 | 562.617031358 |
| special | total_length_mm | 150.273196902 | 155.658088060 | 151.870591957 | 150.760695041 | 8808.494333498 |
| special | propagation_loss_db | 0.751365985 | 0.778290440 | 0.759352960 | 0.753803475 | 44.042471667 |
| special | arc_count | 2.000000000 | 2.000000000 | 2.000000000 | 2.000000000 | 116.000000000 |
| special | total_bend_angle_rad | 1.100093827 | 3.131592612 | 1.940058729 | 1.555483228 | 112.523406272 |
| special | bend_loss_db | 1.673816142 | 4.764784724 | 2.951840594 | 2.366700795 | 171.206754435 |
| special | known_non_crossing_loss_db | 2.425182126 | 5.543075164 | 3.711193553 | 3.120504270 | 215.249226103 |
| global | line_length_mm | 16.175000000 | 265.775000000 | 123.314994731 | 140.637500000 | 63137.277302140 |
| global | arc_length_mm | 5.500469136 | 15.707963268 | 15.027406943 | 15.707963268 | 7694.032355007 |
| global | total_length_mm | 31.882963268 | 281.482963268 | 138.342401674 | 151.635389828 | 70831.309657147 |
| global | propagation_loss_db | 0.159414816 | 1.407414816 | 0.691712008 | 0.758176949 | 354.156548286 |
| global | arc_count | 2.000000000 | 2.000000000 | 2.000000000 | 2.000000000 | 1024.000000000 |
| global | total_bend_angle_rad | 1.100093827 | 3.141592654 | 3.005481389 | 3.141592654 | 1538.806471001 |
| global | bend_loss_db | 1.673816142 | 4.780000000 | 4.572903817 | 4.780000000 | 2341.326754435 |
| global | known_non_crossing_loss_db | 2.425182126 | 6.187414816 | 5.264615826 | 5.310039816 | 2695.483302721 |

Ordinary routes each contain two quarter arcs and yield 4.78 dB bend loss. Special routes also contain two arcs but have variable sweep: bend loss 1.673816 to 4.764785 dB. Mean known loss is 5.463071 dB ordinary versus 3.711194 dB special. These are geometry-dependent estimates, not evidence special routing is globally better: crossing loss remains unavailable.

## 5. Physical crossing angles
Angles are consumed from the existing Step E.1 physical event JSONL, not recomputed from raw segment events. Source Excel hashes are matched to E.1 and the event file SHA-256 is recorded in the loss summary. No 130,816-pair collision rerun was needed.
All 55,935 physical cross records have finite angles in [0,pi/2]. Degrees: min 2.836285984, max 90, mean 78.635766587, median 90.
Histogram uses [lower,upper), except final [80,90]. Thus boundaries are counted exactly once.

| Degrees | Count |
| --- | ---: |
| 0-10 | 886 |
| 10-20 | 622 |
| 20-30 | 1041 |
| 30-40 | 1621 |
| 40-50 | 2008 |
| 50-60 | 2679 |
| 60-70 | 3814 |
| 70-80 | 3918 |
| 80-90 | 39346 |

Coarse bins: <30 = 2,549; 30<=angle<=60 = 6,308; >60 = 47,078. Histogram and coarse totals both equal 55,935.
Travel-direction reversal invariance is inherited from the physical layer and covered again by the new tests.

## 6. Per-waveguide burden
All 512 per-waveguide records include physical_cross_count and angle min/max/mean. With no crossings these are null, never fabricated zero-degree angles.

| Waveguide | Cross count | Min deg | Max deg | Mean deg |
| --- | ---: | ---: | ---: | ---: |
| 34 | 473 | 2.836286 | 90.000000 | 84.495910 |
| 177 | 446 | 2.836286 | 90.000000 | 83.557907 |
| 290 | 409 | 2.836286 | 90.000000 | 81.995376 |
| 265 | 406 | 2.836286 | 90.000000 | 82.206689 |
| 9 | 378 | 2.836286 | 90.000000 | 82.341136 |
| 345 | 364 | 2.836286 | 90.000000 | 78.195305 |
| 35 | 353 | 2.836286 | 90.000000 | 80.062362 |
| 291 | 353 | 2.836286 | 90.000000 | 80.288734 |
| 433 | 352 | 2.836286 | 90.000000 | 80.045210 |
| 185 | 349 | 2.836286 | 90.000000 | 81.179318 |

Incident counts sum to 111,870 = twice 55,935, because each crossing belongs to two waveguides. Pair-local physical points are not globally deduplicated across different route pairs.

## 7. PNG output
outputs/step_8_5_legacy_512_smoothed.png: actual Line and Arc primitives, blue ordinary and orange independent special-Z; equal x/y scale in mm, no crossing-point markers.
scripts/render_legacy_512_smoothed.ps1 uses Windows System.Drawing DrawLine/DrawArc with reversed screen-angle sign for y-down rendering. It does not plot orthogonal skeletons. The framing rectangle is a data viewport, not a newly inferred board x-boundary. Display stroke width is not physical waveguide width.
No Matplotlib/Pillow or other dependencies were installed. PowerShell initially blocked script execution; only the drawing subprocess uses -ExecutionPolicy Bypass. No persistent execution policy was changed.
Image was inspected; label overlap and excessive whitespace were corrected. Rendering rasterizes analytic arcs for display, while all lengths/losses remain analytically calculated.

## 8. Tests and integration checks
17 new tests: line/arc length contribution, mm/cm, 10mm=>0.05dB, 90/45-degree bend values, CW/CCW, ordinary and special arc traversal, known-loss sum, crossing-loss non-call, angle reversal/counts, null no-cross angles, no mutation, mismatched radius and invalid angles.
317/317 direct test functions passed; warnings=0. Existing 300 tests remained passing.
Integration: analytic=512, ordinary=454, special=58; positive finite length and nonnegative known losses for every route; all 55,935 angles valid; histogram counts complete; per-route burden sum correct; source files, geometry, waveguides and allocator unchanged.
A mock guarded crossing_loss during computation and confirmed zero calls. Its original NotImplementedError remains in place.

## 9. Runtime, outputs and reproduction
Final successful analysis+PNG runtime: 1.185124 seconds, before summary serialization. This reuses existing physical events; it is not a full collision-validation timing. Initial blocked render attempt excluded.
- scripts/analyze_legacy_512_loss_v01.py
- src/loss_analysis.py
- tests/test_loss_analysis.py
- scripts/render_legacy_512_smoothed.ps1
- outputs/step_8_5_legacy_512_loss_summary.json
- outputs/step_8_5_legacy_512_plot_geometry.json
- outputs/step_8_5_legacy_512_smoothed.png
Summary contains aggregate/per-waveguide data and the top ten, not the 55,935 full crossing records.
Run from project root: .venv\Scripts\python.exe -B -m scripts.analyze_legacy_512_loss_v01 <legacy AutoRouter directory>.

## 10. Missing model and conclusions
Crossing angle available; crossing loss unavailable. No table, fit, interpolation, fixed crossing penalty or loss estimate was invented.
512 analytic geometries now have propagation and bend loss estimates. This is NOT complete optical loss and NOT collision-free routing. Finite-width/clearance, optimization, special placement changes, allocator changes, 3D and subsequent stages were not performed.
