# Step 8.5-H: Double-Cross Pair Topology Audit V0.1

## 1. Scope and provenance
Diagnostic only. Existing E.1 physical event SHA-256 matches BOTH F loss summary and G multi-crossing summary:
af7e4edffc63e9f1193449494c834f73666ad5b15830a9de9d6185ea3a2e3eb8
55,935 physical crosses in 49,502 pairs: 43,069 single, exactly 6,433 double, zero higher-multiplicity pairs.
Geometry, preparations and A+G1+S1 assignments were deterministically reconstructed from the existing legacy snapshot with the same configuration. This invokes the current allocator to reproduce its results; no policy or stored assignment was changed. Source hashes matched F. Assigned=454, unsupported_geometry=58 remains unchanged.
Only the 6,092 ordinary-ordinary double pairs were rechecked against the original axis-aligned skeleton API. No global smoothed collision, physical consolidation, losses or crossing angles were recomputed.
Raw segment provenance comes from the E event JSONL: pair IDs and coordinates were matched within 1e-9; normalized progress also verifies each point against the indicated analytic segment. Earlier raw JSONL has no independently recorded source hash; it is protected unchanged during this audit and cross-validated against the current geometry/physical records.

## 2. Added files/interfaces
- src/double_cross_audit.py: split_cross_pairs, route_pair_type, geometry_composition, segment_topology, normalized_progress, skeleton_comparison, track_difference, category_range_overlap.
- scripts/analyze_legacy_512_double_cross_v01.py: deterministic integration audit.
- tests/test_double_cross_audit.py.

## 3. Pair composition
| Composition | Count | Percentage |
| --- | ---: | ---: |
| ordinary-ordinary | 6092 | 94.699207% |
| ordinary-special | 341 | 5.300793% |
| special-special | 0 | 0.000000% |

| Route type | Count |
| --- | ---: |
| Z-Z | 2698 |
| U-U | 3735 |
| U-Z | 0 |

Detailed table uses ORIGINAL input travel direction for Z; special remains separate. Algorithmic direction, based on the existing endpoint canonicalization, is recorded separately and must not be confused with original direction.

| Detailed type | Count |
| --- | ---: |
| bottom_to_topZ-bottom_to_topZ | 1159 |
| bottom_to_topZ-top_to_bottomZ | 833 |
| bottom_to_topZ-specialZ | 188 |
| bottomU-bottomU | 1832 |
| specialZ-top_to_bottomZ | 153 |
| top_to_bottomZ-top_to_bottomZ | 365 |
| topU-topU | 1903 |

Unlisted combinations are zero: topU-bottomU, any U-Z and special-special. U-U contributes 3,735 pairs (58.060%); Z-Z contributes 2,698 (41.940%).

## 4. Segment topology
Each physical point is joined to raw segment events. Multiple matching raw pieces would be retained as join labels rather than arbitrarily selecting a segment type. Line-Arc and Arc-Line are canonicalized here as Arc-Line; point ordering is by coordinate, not time or creation sequence.

| Two-intersection combination | Pairs |
| --- | ---: |
| Arc-Line + Arc-Line | 2631 |
| Arc-Line + Line-Line | 723 |
| Arc-Arc + Arc-Arc | 393 |
| Arc-Arc + Arc-Line | 730 |
| Line-Line + Line-Line | 1956 |

4477 / 6,433 pairs (69.594%) have at least one arc-involved intersection.
8231 / 12,866 crossings (63.975%) involve an arc. This measures membership in a bend, not distance to a bend.
Arc-Line + Arc-Line is the largest combination (2,631). Arc involvement is common, but does NOT establish that smoothing created the second crossing; see the skeleton comparison.

## 5. Crossing separation
| Statistic | mm |
| --- | ---: |
| min | 0.547151716 |
| max | 120.416085884 |
| mean | 36.340656701 |
| median | 33.147181276 |

| Distance bin mm | Pairs |
| --- | ---: |
| <.125 | 0 |
| [.125,.175) | 0 |
| [.175,1) | 1 |
| [1,5] | 38 |
| >5 | 6394 |

6,394 pairs have separation >5 mm. Thus most double-crosses are spatially separated, not tiny duplicate-coordinate artifacts. These bins are descriptive, not new invalidity thresholds.

## 6. Normalized path progress
Progress = analytic arclength from original route start to point / total analytic length. Line uses unit-direction projection; Arc uses signed sweep progress. At segment joins all associated progress values must agree within tolerance. Range checks reject off-segment data.
Each pair contributes four observations: two points on each of two routes. Total 25,732 route-point observations. No deduplication across different pairs is intended.

| Progress bin | Observations | Percentage |
| --- | ---: | ---: |
| [0,.1) | 806 | 3.132287% |
| [.1,.25) | 4631 | 17.997046% |
| [.25,.75) | 14215 | 55.242500% |
| [.75,.9) | 5362 | 20.837867% |
| [.9,1] | 718 | 2.790300% |

Only 718 observations (2.790%) lie in the last 10%; 6,080 (23.628%) lie in the last quarter. The middle half contains 14,215 (55.242%). Therefore these double-cross observations are NOT predominantly near the destination under the stated progress bins.
This is not a refutation of the paper's multi-waveguide-crossing endpoint observation: double-cross pairs are a different population, and direction here follows original input, not allocator endpoint canonicalization.

## 7. Skeleton versus smoothed
| Classification | Ordinary pairs |
| --- | ---: |
| skeleton_2_to_smooth_2 | 6092 |
| skeleton_1_to_smooth_2 | 0 |
| skeleton_0_to_smooth_2 | 0 |
| other | 0 |

All 6,092 ordinary-ordinary double pairs already have two raw skeleton cross events, with no skeleton touch or overlap. The skeleton API treats endpoints differently from the physical layer, but no such endpoint ambiguity occurred in this audited subset.
Smoothing-created double pairs in this subset: zero. This does NOT assert that smoothing never changes crossings outside the selected double-pair population; the Step E aggregate changes remain valid. Special-Z has no corresponding assigned ordinary skeleton, so its 341 pairs are not forced into this comparison.

## 8. Track distance and ordering
| Track difference statistic | Value |
| --- | ---: |
| min | 1 |
| max | 221 |
| mean | 41.788411030860146 |
| median | 25.0 |

| abs track-index difference | Pairs |
| --- | ---: |
| 0 | 0 |
| 1 | 258 |
| 2-5 | 662 |
| 6-20 | 1700 |
| >20 | 3472 |

All 454 ordinary assigned tracks are exclusive. Same-track errors: zero.
Within ordinary double pairs: 4,939 have the same algorithmic group, 1,153 different groups. Scan-order inversions against the CURRENT A+G1+S1 policy: zero. This is policy conformity, not evidence the policy minimizes crossings.
Endpoint-order inversion is defined as (algorithmic_start_x_A-start_x_B)*(algorithmic_end_x_A-end_x_B)<0. Among same-group double pairs, 3,735 have this inversion; these are precisely the U-U population. For U routes the condition expresses nested horizontal endpoint intervals.
Algorithmic sort ranks use the existing group key and assigned subset; bottom U scans ascending, the other groups descending. This audits the actual policy rather than assuming original Excel direction controls sorting.

Algorithmic group pair counts:

| Groups | Pairs |
| --- | ---: |
| bottom_to_topZ / top_to_bottomZ | 1153 |
| bottom_to_topZ / bottom_to_topZ | 929 |
| bottomU / bottomU | 1832 |
| topU / topU | 1903 |
| top_to_bottomZ / top_to_bottomZ | 275 |

## 9. Actual category track ranges
| Algorithmic category | Min y | Max y | Min index | Max index | Count |
| --- | ---: | ---: | ---: | ---: | ---: |
| bottom_to_topZ | 85.175000 | 106.350000 | 458 | 579 | 122 |
| bottomU | 5.025000 | 24.450000 | 0 | 111 | 112 |
| top_to_bottomZ | 106.525000 | 125.250000 | 580 | 687 | 108 |
| topU | 125.425000 | 144.850000 | 688 | 799 | 112 |

Overlap matrix for closed track-index hulls (1 = overlap):

| Category | bottomU | bottom_to_topZ | topU | top_to_bottomZ |
| --- | ---: | ---: | ---: | ---: |
| bottomU | 1 | 0 | 0 | 0 |
| bottom_to_topZ | 0 | 1 | 0 | 0 |
| topU | 0 | 0 | 1 | 0 |
| top_to_bottomZ | 0 | 0 | 0 | 1 |

All off-diagonal entries are false: current category track ranges do NOT overlap, despite absence of a general legacy region-lock implementation. Therefore current evidence does not support overlapping category track ranges as the principal cause.
These are common-track ranges, not envelopes of complete routes: vertical leads and bends may extend outside them. The table is a read-only diagnostic, not an executed counterfactual routing experiment.

## 10. Representative top-U mechanism
Example pair 36 / 37:
{
  "a": {
    "algorithmic_end_x": 130.0,
    "algorithmic_group": "topU",
    "algorithmic_start_x": 101.125,
    "assignment": {
      "reason": null,
      "status": "assigned",
      "track_index": 695,
      "track_y": 126.64999999999999,
      "waveguide_id": 36
    },
    "preparation": {
      "route_type": "u",
      "side": "top",
      "waveguide_id": 36
    },
    "route_type": "topU",
    "special": false
  },
  "b": {
    "algorithmic_end_x": 130.175,
    "algorithmic_group": "topU",
    "algorithmic_start_x": 100.95,
    "assignment": {
      "reason": null,
      "status": "assigned",
      "track_index": 696,
      "track_y": 126.825,
      "waveguide_id": 37
    },
    "preparation": {
      "route_type": "u",
      "side": "top",
      "waveguide_id": 37
    },
    "route_type": "topU",
    "special": false
  },
  "crossings": [
    {
      "angle_deg": 2.836285983685112,
      "point": {
        "x": 102.50304901717382,
        "y": 128.2030490171741
      },
      "progress_a": 0.6892211900429069,
      "progress_b": 0.688203939336805,
      "raw_event_count": 1,
      "segment_indices_a": [
        3
      ],
      "segment_indices_b": [
        3
      ],
      "topology": "Arc-Arc"
    },
    {
      "angle_deg": 2.8362859836852112,
      "point": {
        "x": 128.62195098282606,
        "y": 128.20304901717392
      },
      "progress_a": 0.3107788099570961,
      "progress_b": 0.311796060663198,
      "raw_event_count": 1,
      "segment_indices_a": [
        1
      ],
      "segment_indices_b": [
        1
      ],
      "topology": "Arc-Arc"
    }
  ]
}

Nested horizontal endpoint intervals combined with current left-to-right ordering and track depths give a concrete skeleton-level mechanism to investigate. It is stronger evidence than blaming special-Z or smoothing globally, but no alternate policy has been executed in this step.

## 11. High-burden waveguides and pairs
| Waveguide | Participating double pairs |
| --- | ---: |
| 34 | 103 |
| 290 | 94 |
| 177 | 89 |
| 265 | 83 |
| 9 | 74 |
| 345 | 73 |
| 291 | 71 |
| 433 | 69 |
| 35 | 65 |
| 60 | 59 |
| 61 | 59 |
| 62 | 59 |
| 63 | 59 |
| 266 | 59 |
| 267 | 59 |
| 268 | 59 |
| 334 | 59 |
| 335 | 59 |
| 336 | 59 |
| 438 | 59 |

Every pair has the same multiplicity (two), so top pair ranking is defined by greatest Euclidean separation, then canonical IDs; it is not an invented risk score.

| Pair | Separation mm | Topology |
| --- | ---: | --- |
| 34 / 177 | 120.416086 | Arc-Arc + Arc-Line |
| 301 / 302 | 120.229636 | Arc-Arc + Arc-Arc |
| 302 / 303 | 120.229636 | Arc-Arc + Arc-Arc |
| 301 / 303 | 120.223295 | Arc-Arc + Arc-Arc |
| 31 / 301 | 113.555098 | Arc-Line + Arc-Line |
| 31 / 302 | 113.086880 | Arc-Line + Arc-Line |
| 31 / 303 | 112.476140 | Arc-Line + Arc-Line |
| 301 / 340 | 104.613792 | Arc-Line + Arc-Line |
| 301 / 339 | 104.445384 | Arc-Line + Arc-Line |
| 302 / 340 | 104.445384 | Arc-Line + Arc-Line |
| 302 / 339 | 104.280826 | Arc-Line + Arc-Line |
| 303 / 340 | 104.280826 | Arc-Line + Arc-Line |
| 301 / 338 | 104.280826 | Arc-Line + Arc-Line |
| 303 / 339 | 104.115193 | Arc-Line + Arc-Line |
| 302 / 338 | 104.115193 | Arc-Line + Arc-Line |
| 303 / 338 | 103.946652 | Arc-Line + Arc-Line |
| 9 / 34 | 102.076327 | Arc-Line + Arc-Line |
| 338 / 339 | 101.711145 | Arc-Arc + Arc-Arc |
| 339 / 340 | 101.711145 | Arc-Arc + Arc-Arc |
| 338 / 340 | 101.704833 | Arc-Arc + Arc-Arc |

20 deterministic examples are saved, covering closest/farthest, observed U-U/Z-Z and ordinary-special classes, all observed topology combinations, and skeleton-already-double. U-Z, special-special and smoothing-created cases cannot be supplied because none exist in this dataset. No optional case SVG was produced.

## 12. Evidence-supported conclusions and ONE next experiment
1. Double pairs are primarily ordinary-ordinary (94.699%), with U-U the largest type. Special-Z cannot explain most of this population.
2. 69.594% of pairs involve at least one arc; nevertheless all audited ordinary double pairs already exist before smoothing.
3. The last 10% of route progress accounts for only 2.790% of observations: not mainly destination-local.
4. Smoothing-created double pairs: zero within the 6,092 ordinary selected pairs; no inference is made about all other pairs.
5. The four actual assigned track hulls are disjoint. Adding region separation is not the leading hypothesis supported by this range audit.
6. The strongest candidate is the interaction of ordering with track depth and endpoint topology in the existing skeleton policy. No scan-order implementation inversion was found. Z-specific policy interactions remain a separate question; 341 ordinary-special pairs can be studied later.
Recommended sole next experiment: reverse only the top-U primary algorithmic start.x sort direction, retaining its tie-breakers, its current track pool/scan direction, all other groups and special placement. Measure whether the 1,903 topU-topU doubles decline and whether new interactions appear. This is a proposed falsifiable experiment, NOT a change made here and NOT a claim of guaranteed improvement.

## 13. Tests, checks and runtime
15 new tests cover exactly-two versus single/higher multiplicity, U/Z and special composition, segment topology, line/arc progress, reversal, actual synthetic skeleton/smoothed comparison, comparison categories, track uniqueness/difference, range overlap, canonical ordering and nonmutation.
352/352 direct test functions passed (original 337 + 15), 0 warnings. No dependencies installed.
All 6,433 JSONL records independently checked for unique canonical pairs and exactly two audited crossings. Geometry/source/allocator and all prior src/output hashes remain unchanged.
Final audit runtime: 1.856532 seconds, before summary serialization. Includes reconstruction, target-only skeleton queries, provenance/progress analysis, hashing and outputs. No full collision pass.

## 14. Outputs and limits
- outputs/step_8_5_legacy_512_double_cross_summary.json
- outputs/step_8_5_legacy_512_double_cross_pairs.jsonl (all 6,433 records)
- outputs/step_8_5_double_cross_examples.json (20 examples)
Re-run: .venv\Scripts\python.exe -B -m scripts.analyze_legacy_512_double_cross_v01.
This remains descriptive topology audit, not finite-width/clearance or loss assessment. Pair progress, angle and distance statistics are not new hard constraints. It does not generalize the paper's three-point criterion to multi-cross pairs.
No ordering, track, allocator, region lock, special placement, K backtracking, optimization or 3D change was made. Stop at Step 8.5-H.
