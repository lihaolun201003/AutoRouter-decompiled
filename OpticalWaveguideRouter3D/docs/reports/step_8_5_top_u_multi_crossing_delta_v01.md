# Step 8.5-J: Multi-Waveguide Crossing Differential Audit V0.1

## 1. Scope and provenance
Read-only comparison of official Control ascending A+G1+S1 and the previously run experimental top-U descending Variant. No allocator, routing, collision, physical consolidation, loss or angle recalculation was performed.
Inputs: Control318 detected triplets, Control physical JSONL, Variant physical JSONL, Step I isolation summary, original plotting geometry and existing Variant SVG. Existing multi_crossing.py was reused to derive345 Variant detections.
Control physical SHA-256 matches Step F/I records. Step I had not recorded a Variant event checksum; this audit records one and verifies event/pair counts against I. This is not a claim of pre-existing cryptographic validation for the Variant artifact.
- control_physical: af7e4edffc63e9f1193449494c834f73666ad5b15830a9de9d6185ea3a2e3eb8
- variant_physical: e168bc1f68bc70e47a95444dd35719655930c8750e17c4c98d3e88d0baf27a50
All prior src/output file hashes stayed unchanged. Default baseline was not modified; no second sorting variant was tried.

## 2. Unchanged criterion and severity indicator
spacing=.125mm, tol=1e-9mm. Three routes must have exactly one cross per pair. At least two sides shorter than spacing-tol meet the existing criterion. Boundary does not count as short. Track pitch .175mm is not used as the threshold.
Severity descriptor: sort the three sides s1<=s2<=s3; second_shortest_margin_mm=.125-s2. A larger margin means the second side is deeper inside the threshold, not greater optical loss or a fabrication risk measurement. With the actual tolerance rule, definite detection requires margin>tol; a tiny positive margin within tol is still boundary. This descriptor does not change classification or introduce an objective.

## 3. Exact canonical triplet differences
| Set | Count |
| --- | ---: |
| Stable | 204 |
| Removed | 114 |
| Added | 141 |
| Net change | +27 |

Verified:204+114=318;204+141=345;141-114=27. The actual turnover is255 triplets, not27. Complete added/removed records are saved with Control/Variant points, side lengths, angles and opposite-state provenance.

## 4. Top-U membership and composition
| Set | 0 top-U | 1 top-U | 2 top-U | 3 top-U |
| --- | ---: | ---: | ---: | ---: |
| stable | 204 | 0 | 0 | 0 |
| removed | 0 | 0 | 114 | 0 |
| added | 0 | 5 | 121 | 15 |

All141 added and all114 removed contain top-U. No-top-U invariant passes; all204 stable triplets contain no top-U. All changed cases are therefore directly incident to the routes whose track mapping changed.
Detailed grouping: topU-topU-topU15 added; topU-topU-other121 added and114 removed; topU-other-other5 added; no-topU204 stable.

| Set | ordinary/ordinary/ordinary | ordinary/ordinary/special | ordinary/special/special | special/special/special |
| --- | ---: | ---: | ---: | ---: |
| stable | 132 | 72 | 0 | 0 |
| removed | 90 | 24 | 0 | 0 |
| added | 108 | 33 | 0 | 0 |

## 5. Graph and eligible SET audit
Triangle enumeration is canonical a<b<c. The Control triangles were streamed through exact Variant pair-membership checks; Variant triangle/eligible totals were independently enumerated. This gives set intersection/difference cardinalities without materializing millions of tuple objects. It does not infer equality merely from equal totals.

| Set family | Stable | Removed | Added |
| --- | ---: | ---: | ---: |
| graph_set_diff | 1835220 | 228328 | 0 |
| eligible_set_diff | 1222071 | 0 | 0 |

Control graph2,063,548 -> Variant1,835,220: Variant graph triangles form a subset, with228,328 removed and no added.
The legacy-eligible SET is exactly identical:1,222,071 stable,0 removed,0 added.
All141 added triplets were eligible in Control but did not meet the distance criterion. All114 removed remain eligible in Variant but no longer meet it. None of these changed detections is explained by a missing pair, a new graph triangle or a change from multiple to single cross. Three pair multiplicities for every changed triplet are saved in both arms.
Thus the measured mechanism is changed locations of the three already-existing unique pair-crossing points within the same eligible triplets, causing threshold entry/exit. This confirms, rather than assumes, the geometric interpretation suggested in I.

## 6. Added and removed side/severity distributions
| Set | Metric | Min mm | Mean mm | Median mm | Max mm |
| --- | --- | ---: | ---: | ---: | ---: |
| added | s1 | 0.003760889 | 0.035007960 | 0.029168699 | 0.097589905 |
| added | s2 | 0.005027248 | 0.073319483 | 0.062202405 | 0.124336361 |
| added | s3 | 0.005628879 | 0.081626873 | 0.067063568 | 0.152317679 |
| added | second_shortest_margin_mm | 0.000663639 | 0.051680517 | 0.062797595 | 0.119972752 |
| removed | s1 | 0.007921644 | 0.035916560 | 0.029168699 | 0.087983775 |
| removed | s2 | 0.010423600 | 0.071239245 | 0.062202405 | 0.124336361 |
| removed | s3 | 0.011231865 | 0.080208963 | 0.067063568 | 0.152317679 |
| removed | second_shortest_margin_mm | 0.000663639 | 0.053760755 | 0.062797595 | 0.114576400 |

Descriptive margin bins (not additional criterion):

| Margin mm | Added | Removed |
| --- | ---: | ---: |
| (0,.001] | 6 | 8 |
| (.001,.01] | 9 | 7 |
| (.01,.05] | 39 | 25 |
| >.05 | 87 | 74 |

Only15/141 added (10.638%) have margin<=.01mm;87/141 (61.702%) exceed .05mm. Hence most additions are NOT just barely crossing the threshold.
Added mean margin .051680517mm is slightly smaller than removed mean .053760755mm; medians are essentially identical (.062797595mm). This does not support saying added cases are uniformly tighter than removed cases. However there are more added cases, and the tightest added s2=.005027248mm versus removed minimum s2=.010423600mm. The distributions show a mixed tradeoff with some tightly clustered additions.
Margin sums, if consulted, are unweighted descriptive sample totals; they are not an optimization objective or evidence of net optical harm.

## 7. Stable severity differences
204 stable: improved0, worsened0, unchanged-with-tol204. Delta margin min/max/mean/median all0. Control and Variant stable side and angle statistics are identical; these triplets contain no top-U.
No stable-improved/worsened examples can be selected because none exist.

## 8. Crossing-angle auxiliary audit
Angles are taken from the existing physical pair data, in degrees. Each triplet contributes its minimum and mean of three angles. Shared pair intersections can occur in multiple triplets; this is triplet-weighted description, not a globally unique crossing population.

| Set | Min of minima | Mean of minima | Median of minima | Mean of triplet means | Triplets with <20 deg |
| --- | ---: | ---: | ---: | ---: | ---: |
| added | 15.203604093 | 25.918653265 | 21.565185015 | 59.980734027 | 26 |
| removed | 15.203604093 | 26.955477507 | 26.491570200 | 60.008925084 | 18 |
| stable | 15.203604093 | 29.716017179 | 26.491570200 | 60.046473018 | 30 |

Added contains26 small-angle triplets versus18 removed. Added median minimum angle21.565185 degrees versus26.491570 removed. Thus despite Step I's GLOBAL below20-cross count improvement1508->984, the added multi-crossing subset includes more small-angle triplets than the removed subset.
20 degrees remains descriptive background, not a hard constraint; crossing_loss was never called.

## 9. Top-U incident burden
| Set | Waveguide | Added/removed triplet participation |
| --- | ---: | ---: |
| added | 332 | 12 |
| added | 36 | 11 |
| added | 50 | 9 |
| added | 51 | 9 |
| added | 155 | 9 |
| added | 286 | 9 |
| added | 331 | 9 |
| added | 37 | 8 |
| added | 48 | 8 |
| added | 49 | 7 |
| added | 55 | 6 |
| added | 285 | 6 |
| added | 38 | 5 |
| added | 42 | 5 |
| added | 52 | 5 |
| added | 54 | 5 |
| added | 66 | 5 |
| added | 97 | 5 |
| added | 100 | 5 |
| added | 289 | 5 |
| removed | 485 | 13 |
| removed | 457 | 12 |
| removed | 142 | 8 |
| removed | 265 | 8 |
| removed | 465 | 8 |
| removed | 332 | 7 |
| removed | 128 | 6 |
| removed | 129 | 6 |
| removed | 164 | 6 |
| removed | 461 | 6 |
| removed | 464 | 6 |
| removed | 55 | 5 |
| removed | 64 | 5 |
| removed | 140 | 5 |
| removed | 441 | 5 |
| removed | 450 | 5 |
| removed | 42 | 4 |
| removed | 54 | 4 |
| removed | 95 | 4 |
| removed | 97 | 4 |

Counts are per-waveguide incident triplets and do not sum to triplet totals because changed triplets may contain multiple top-U routes.

## 10. Representative cases
Eight cases saved: two nearest-threshold and two largest-margin added, plus the corresponding four removed. No stable improved/worsened case exists, so none was fabricated. Case count remains below12.
Each case includes route IDs, top-U membership, both arms' physical crossing points, three sides, angles and track metadata. Control assignments are read from stored H records. Variant common-track y/index is recovered from the existing SVG first-arc endpoint (y=(880-svg_y)/5, index=(y-5.025)/.175) and validated against grid tolerance. This is labeled derived geometry metadata, not a fresh allocator run. Special tracks remain null/unsupported.
No optional case SVG was needed; the saved JSON contains full geometry for inspection.

## 11. Recommendation
The reversal's measured benefits remain: -1,903 doubles, -3,806 physical crosses, -1,903 crossing pairs, -524 globally below20 crossings, increased mean angle, unchanged known-loss mean/max.
Adverse evidence is more than a small boundary artifact:141 additions replace114 removals;87 additions have margin>.05mm, and26 added versus18 removed contain a below20 crossing. On the other hand, average added margin is slightly smaller than removed and stable cases do not worsen.
Recommendation C: keep the Variant as an experimental candidate, NOT an automatic baseline replacement. This is a mixed tradeoff; the evidence does not justify declaring either total superiority or uniformly worse clusters. A formal adoption decision needs an explicit acceptance policy for multi-crossing tradeoffs; no such objective is invented here. No second ordering or optimizer was implemented.

## 12. Tests and runtime
13 new tests cover canonical sets, set/count identities, second-shortest extraction/margin/ranking, stable delta, no-top-U failure, composition, graph/eligible differences even with equal counts, angles, nonmutation and deterministic results.
377/377 direct test functions passed (364 previous +13 new); warnings0. No dependencies installed.
Integration verified318/345 counts, exact set identities, unchanged eligible membership, no-top-U invariant, all prior file hashes and correct labels for the141/114 saved differences.
Audit runtime: 12.005036 seconds before summary serialization. Includes parsing, graph membership/enumeration, existing-criterion evaluation, severity/provenance analysis and outputs. No routing or full collision run.

## 13. Outputs
- scripts/analyze_top_u_multi_crossing_delta_v01.py
- src/multi_crossing_delta.py
- tests/test_multi_crossing_delta.py
- outputs/step_8_5_top_u_multi_crossing_delta_summary.json
- outputs/step_8_5_top_u_multi_crossing_added.jsonl
- outputs/step_8_5_top_u_multi_crossing_removed.jsonl
- outputs/step_8_5_top_u_reverse_multi_crossings.jsonl (complete345 Variant detections)
- outputs/step_8_5_top_u_multi_crossing_examples.json
Stable per-triplet geometry remains available by canonical ID in the existing318 Control and new345 Variant files; summary also stores both stable distributions and delta statistics.
Run from project root: .venv\Scripts\python.exe -B -m scripts.analyze_top_u_multi_crossing_delta_v01.

Control ascending remains the official baseline. Stop at Step8.5-J; no routing changes, finite-width/clearance claims, crossing loss,3D or next-stage work.
