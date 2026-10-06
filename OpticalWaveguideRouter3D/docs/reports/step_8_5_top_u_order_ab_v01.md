# Step 8.5-I: Top-U Primary Ordering Reversal A/B Experiment

## 1. Control and the one experimental variable
Control is the official A+G1+S1 baseline. Code inspection confirmed its ascending sort tuple:
`(group, algorithmic_start.x, algorithmic_end.x, start.pmt_id, end.pmt_id, waveguide.id)`.
Top-U is group 0 and scans tracks descending. The existing primary direction is ascending; it was not inferred from the task wording.
TrackPolicyConfig adds top_u_primary_order='ascending' by default. Experimental Variant explicitly sets 'descending'. Only group 0 replaces the primary x with -x; every other tuple entry and the full track scanning/allocation logic stay unchanged. Invalid options raise ValueError.
The secondary x, PMT IDs and waveguide ID tie-breakers retain ascending order. This is NOT reverse=True on the entire key. Other groups, grid G1, exclusive ownership A, S1 and special midpoint geometry are unchanged.
src/router_2d.py contains this small opt-in change; no router clone was introduced. scripts/experiment_top_u_order_v01.py invokes exactly one Variant. Default baseline remains ascending.

## 2. Isolation and invariants
- non_top_assignments_unchanged: True
- top_assigned_ids_unchanged: True
- top_track_pool_unchanged: True
- grid_unchanged: True
- non_top_geometry_unchanged: True
All 112 top-U route-to-track mappings changed; the same 112 assigned IDs and the same index set 688..799 were preserved.
Every non-top-U TrackAssignment is equal route by route, including bottom-U, both Z groups and all 58 unsupported special-Z entries. Every non-top-U analytic geometry is exactly equal between Control and Variant.
Control was rebuilt with default settings and checked against prior per-route lengths/losses and all prior H-recorded assignments. Baseline physical data SHA-256 matches F and G. Prior output files were hash-checked unchanged.
Variant: input512; assigned454; unsupported58; no_available_track0; ordinary skeleton454; ordinary smoothed454; special58; analytic total512. Endpoints, continuity, radius, tangent continuity and finite positive lengths passed for every route; self cross/touch/overlap all zero.

## 3. Primary endpoint and skeleton diagnosis
| Metric | Control | Variant | Absolute change | Relative change |
| --- | ---: | ---: | ---: | ---: |
| topU-topU physical double pairs | 1903 | 0 | -1903 | -100% |
| topU-topU skeleton double pairs | 1903 | 0 | -1903 | -100% |

All 6,216 unordered top-U pairs were checked in each skeleton. The same 1,903 nested endpoint pairs exist in both arms: nested pair relation cannot change with track assignment. Nested pairs with doubles: 1,903/1,903 (100%) -> 0/1,903 (0%) in both skeleton and physical geometry.
Thus the improvement precedes smoothing and supports the endpoint-nesting/track-depth mechanism for these top-U pairs.

## 4. Secondary double-cross metrics
| Metric | Control | Variant | Delta |
| --- | ---: | ---: | ---: |
| Total double pairs | 6433 | 4530 | -1903 |
| ordinary-ordinary | 6092 | 4189 | -1903 |
| ordinary-special | 341 | 341 | 0 |
| special-special | 0 | 0 | 0 |
| U-U | 3735 | 1832 | -1903 |
| U-Z | 0 | 0 | 0 |
| Z-Z | 2698 | 2698 | 0 |
| topU-topU | 1903 | 0 | -1903 |
| bottomU-bottomU | 1832 | 1832 | 0 |
| bottomU-topU | 0 | 0 | 0 |
| ordinaryZ-topU | 0 | 0 | 0 |
| specialZ-topU | 0 | 0 | 0 |
| ordinaryZ-ordinaryZ | 2357 | 2357 | 0 |
| ordinaryZ-specialZ | 341 | 341 | 0 |
| specialZ-specialZ | 0 | 0 | 0 |

Higher-than-two cross pairs remain zero. The 1,903-pair reduction is confined to topU-topU in these count comparisons. Bottom-U and Z-Z double counts do not change.

## 5. Global physical crossings
Exactly 130,816 unordered Variant route pairs were run through the unchanged analytic raw intersection API and physical consolidation layer.

| Metric | Control | Variant | Delta |
| --- | ---: | ---: | ---: |
| cross_points | 55935 | 52129 | -3806 |
| cross_pairs | 49502 | 47599 | -1903 |
| touch | 0 | 0 | 0 |
| overlap | 0 | 0 | 0 |
| touch_pairs | 0 | 0 | 0 |
| overlap_pairs | 0 | 0 | 0 |

Variant raw segment counts: cross52,126; touch12; overlap0. The existing three special midpoint contacts still consolidate to three physical crosses; this layer's semantics were not altered.
Physical counts are pair-local coordinate-consolidated intersections, not globally unique coordinates across different pairs. Reduction: 3,806 physical crosses and 1,903 crossing pairs.

## 6. Top-U interaction audit
| Interaction | Control cross points | Variant cross points | Control cross pairs | Variant cross pairs | Control doubles | Variant doubles |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| topU-topU | 6833 | 3027 | 4930 | 3027 | 1903 | 0 |
| topU-bottomU | 0 | 0 | 0 | 0 | 0 | 0 |
| topU-ordinaryZ | 8502 | 8502 | 8502 | 8502 | 0 | 0 |
| topU-specialZ | 2198 | 2198 | 2198 | 2198 | 0 | 0 |
| topU-all | 17533 | 13727 | 15630 | 13727 | 1903 | 0 |

No increase in topU-bottomU, topU-ordinaryZ or topU-specialZ crossing/double counts was observed. This addresses transfer of pair-crossing counts, not equality of all point coordinates or absence of other spacing-based side effects.

## 7. Multi-waveguide crossing: important tradeoff
| Metric | Control | Variant | Delta |
| --- | ---: | ---: | ---: |
| detected | 318 | 345 | 27 |
| boundary | 2 | 2 | 0 |
| legacy_eligible | 1222071 | 1222071 | 0 |
| outside | 841477 | 613149 | -228328 |
Control graph candidates2,063,548 -> Variant1,835,220 (-228,328). Outside-assumption candidates841,477 ->613,149 (-228,328). Eligible triangle count remains1,222,071.
Eligible multi-waveguide crossings increase318 ->345 (+27, +8.491%). Boundary remains2. This is a real measured adverse tradeoff under the unchanged spacing=.125mm criterion; it must not be hidden by the double-cross improvement.
The increase cannot be explained merely by a larger eligible count, because that count did not increase. Changed top-U crossing locations can change the three-point distances; this is a plausible geometric interpretation, not an independently established per-triplet cause in this experiment. Unassessed outside-assumption candidates are not declared safe.

## 8. Crossing angles
| Metric | Control | Variant | Delta |
| --- | ---: | ---: | ---: |
| count | 55935 | 52129 | -3806 |
| min | 2.8362859836847427 | 2.8362859836848604 | 1.176836406102666e-13 |
| mean | 78.63576658695646 | 79.82164188239051 | 1.1858752954340446 |
| median | 90.0 | 90.0 | 0.0 |
| below_20_count | 1508 | 984 | -524 |

Angles are degrees here. Minimum remains approximately2.836286 degrees; the tiny reported difference is floating-point scale. Mean increases78.635767 ->79.821642. Median remains90. Below20-degree crossings decrease1,508 ->984 (-524). Control below20 count was read from the existing [0,10)/[10,20) histogram, not guessed.
crossing_loss remains NotImplementedError; a mock guard confirmed the analysis did not call it.

## 9. Known non-crossing loss and length
| Metric | Control mean | Variant mean | Control max | Variant max |
| --- | ---: | ---: | ---: | ---: |
| total_length_mm | 138.342401674115 | 138.342401674115 | 281.482963267949 | 281.482963267949 |
| propagation_loss_db | 0.691712008371 | 0.691712008371 | 1.407414816340 | 1.407414816340 |
| bend_loss_db | 4.572903817256 | 4.572903817256 | 4.780000000000 | 4.780000000000 |
| known_non_crossing_loss_db | 5.264615825627 | 5.264615825627 | 6.187414816340 | 6.187414816340 |

All454 ordinary routes were traversed and verified to have4.78dB bend loss; the estimate is not hard-coded into geometry/loss calculation. Special sweeps and losses stay unchanged.
Global mean/max length, propagation, bend and known non-crossing loss stay unchanged. Individual top-U lengths are redistributed: global minimum length31.882963 ->21.432963mm; known-loss median5.310040 ->5.349540dB. Aggregate mean equality does not imply per-waveguide equality. The top-U endpoint spans and total assigned track-y sum are unchanged, consistent with total length conservation for these U templates.
Known loss excludes crossing loss; no complete optical loss or fabrication feasibility claim is made.

## 10. Track-range isolation
| Category | Control indices | Variant indices |
| --- | --- | --- |
| topU | 688..799 | 688..799 |
| bottomU | 0..111 | 0..111 |
| top_to_bottomZ | 580..687 | 580..687 |
| bottom_to_topZ | 458..579 | 458..579 |

Ranges remain disjoint; all assigned tracks remain exclusive. No region lock or track pool redesign was performed.

## 11. Interpretation and baseline recommendation
Strong evidence supports top-U primary ordering as a cause of the1,903 topU-topU double-crosses in this dataset: a single isolated reversal removes all of them already at skeleton level, without increasing other top-U pair-crossing counts.
The result is not unqualified dominance: multi-waveguide criterion detections rise by27 even while pair crossings and small-angle counts fall. It therefore supports the PRIMARY hypothesis but is not a clean all-metrics improvement. It is neither a simple transfer into topU-other double pairs nor proof that every routing risk improves.
Recommendation: retain the Variant as an experimental candidate; do NOT formally replace the baseline yet. The new345 eligible multi-waveguide detections require review before adoption. No second ordering or other parameter adjustment was tried.

## 12. Tests
12 new tests: default behavior, primary-only reversal, all current tie-breakers, bottom-U unchanged, Z unchanged, special unsupported unchanged, assigned IDs, top-U track set, actual nested-U skeleton comparison, no mutation, invalid option and deterministic repeated calls/input permutation.
364/364 direct test functions passed;0 warnings. Existing352 tests remain passing. No dependency installation.
Integration checked source/prior-output hashes, Control/non-top equality, route/track isolation, route validity and no self intersections. SVG XML checked512 route groups,1,024 true arc commands and no raster image embedding. All4,530 saved Variant double-pair records have unique canonical IDs.

## 13. Runtime
| Stage | Seconds |
| --- | ---: |
| control_load_rebuild_seconds | 0.512907 |
| variant_allocator_geometry_seconds | 0.345873 |
| skeleton_diagnostic_seconds | 0.385060 |
| geometry_self_seconds | 0.046608 |
| variant_raw_collision_seconds | 17.005123 |
| physical_consolidation_seconds | 2.509025 |
| double_cross_analysis_seconds | 0.674832 |
| multi_crossing_seconds | 7.413312 |
| loss_angle_seconds | 0.089612 |
| total_seconds | 30.214109 |

One Variant execution. Timings are wall-clock observations, not benchmark averages. Total includes event writing, preparation checks and serialization overhead; raw collision and consolidation are timed separately per pair. No second parameter variant was evaluated.

## 14. Outputs
- outputs/step_8_5_top_u_order_ab_summary.json
- outputs/step_8_5_top_u_reverse_physical_events.jsonl
- outputs/step_8_5_top_u_reverse_double_cross_pairs.jsonl
- outputs/step_8_5_top_u_reverse_variant.svg (true vector Line/Arc, no crossing markers)
Control SVG and baseline result files were not regenerated or overwritten. No optional comparison SVG was needed.
Run from project root: .venv\Scripts\python.exe -B -m scripts.experiment_top_u_order_v01.

Control remains the official ascending A+G1+S1 baseline. Stop at Step8.5-I; no baseline adoption, bottom-U/Z change, second sorting experiment, rerouting, region lock, loss-table invention,3D or next step.
