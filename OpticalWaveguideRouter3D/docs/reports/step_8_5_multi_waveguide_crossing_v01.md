# Step 8.5-G: Multi-Waveguide Crossing Detection V0.1

## 1. Legacy paper definition versus this implementation
Basis: the section 3.2.1 criterion supplied for Huang Zhijie's thesis, '面向板级高速光互连应用的光波导智能排布技术研究'. Three mutually crossing waveguides produce three pairwise crossing points. At least two sides of their point triangle shorter than spacing d defines a multi-waveguide crossing.
This stage implements that supplied criterion on the project's existing exact physical centerline intersections. It does not reproduce legacy routing/optimization code and does not introduce a generalized criterion for pairs with multiple intersections.

## 2. Spacing and boundary semantics
d = spacing_mm = 0.125 mm; tol = 1e-9 mm. Width 0.05 mm and pitch 0.175 mm are NOT the detection threshold.
- short: length < spacing - tol.
- boundary: abs(length - spacing) <= tol; boundary never counts as short.
- safe: length > spacing + tol.
At least two definite shorts => multi_waveguide_crossing. This takes priority even if the third side is boundary. With fewer than two shorts, any boundary side => boundary, otherwise not_multi_waveguide_crossing. Boundary side incidence is separately recorded. Real data has two boundary triangles and no detected multi with a boundary side.
Equality is not replaced by <=. Coincident/degenerate point triangles are not discarded by an invented positive-area constraint; the supplied distance criterion is used directly.

## 3. Interfaces and data
New src/multi_crossing.py:
- MultiWaveguideCrossing: canonical route_ids, point_ab/ac/bc, side_lengths_mm, short_side_count, spacing_mm, classification, boundary_side_count.
- build_crossing_pair_map: canonical unordered pair -> complete physical cross list.
- audit_pair_multiplicity.
- build_crossing_graph and enumerate_crossing_triangles.
- classify_multi_crossing and detect_multi_waveguide_crossings.
- triplet_composition.
Outside-assumption records have no chosen points, side lengths or short-side count. Existing PhysicalRouteIntersection and every prior algorithm remain unchanged.

## 4. Input provenance and pair multiplicity
Read the existing E.1 physical event JSONL; SHA-256 matched the Step F loss summary. No collision, routing, loss or physical-angle recomputation was performed.
Physical cross count: 55,935. Graph has 510 nodes with at least one cross; the two isolated waveguides remain included in the 512-entry per-waveguide burden table.
Allocator stays 454 assigned and 58 unsupported_geometry; special means independent special-Z analytic geometry.

| Metric | Count |
| --- | ---: |
| cross_pairs_total | 49502 |
| pairs_with_1_cross | 43069 |
| pairs_with_2_crosses | 6433 |
| pairs_with_3_or_more_crosses | 0 |
| pairs_with_multiple_crosses | 6433 |
| max_crosses_per_pair | 2 |

Top 20 pairs by multiplicity (all ties sorted by canonical IDs):

| Pair | Physical crosses |
| --- | ---: |
| 0 / 341 | 2 |
| 1 / 341 | 2 |
| 2 / 276 | 2 |
| 2 / 277 | 2 |
| 3 / 276 | 2 |
| 3 / 277 | 2 |
| 4 / 5 | 2 |
| 4 / 6 | 2 |
| 4 / 7 | 2 |
| 4 / 8 | 2 |
| 4 / 24 | 2 |
| 4 / 25 | 2 |
| 4 / 26 | 2 |
| 4 / 27 | 2 |
| 4 / 74 | 2 |
| 4 / 85 | 2 |
| 4 / 146 | 2 |
| 4 / 163 | 2 |
| 4 / 165 | 2 |
| 4 / 166 | 2 |

## 5. Crossing graph and triangle classification
Undirected adjacency sets are constructed from nonempty pair-map edges. For each ordered edge a<b, intersect neighbors and emit only c>b. Every triplet has a<b<c and appears once. This avoids enumerating C(512,3) and scanning all events per triplet.
All three pair lists must have length one to evaluate the legacy triangle distances. If any list is longer, classification is outside_legacy_single_cross_assumption; no point is arbitrarily selected.

| Metric | Count |
| --- | ---: |
| graph_triangle_candidates | 2063548 |
| legacy_eligible_triangles | 1222071 |
| outside_legacy_assumption_triangles | 841477 |
| multi_waveguide_crossing_count | 318 |
| non_multi_crossing_triangle_count | 1221751 |
| boundary_triangle_count | 2 |

The accounting identities were checked: eligible + outside = candidates; multi + non-multi + boundary = eligible. Outside is NOT equivalent to non-multi or safe.

## 6. Detected-triplet composition
| Composition | Count |
| --- | ---: |
| ordinary/ordinary/ordinary | 222 |
| ordinary/ordinary/special | 96 |
| ordinary/special/special | 0 |
| special/special/special | 0 |

Only detected eligible triplets contribute to this composition table; outside-assumption candidates do not. Counts describe this baseline, not a comparison proving any class of routing superior.

## 7. Per-waveguide burden
participating_multi_crossing_count is the number of detected triplets containing the waveguide, not pair crossing count. Full 512-entry data, including zeros, is in the summary. Incident counts sum to 954 = 3 * 318.

| Waveguide | Special | Participating triplets |
| --- | --- | ---: |
| 74 | False | 13 |
| 485 | False | 13 |
| 457 | False | 12 |
| 245 | False | 9 |
| 85 | False | 8 |
| 102 | False | 8 |
| 103 | False | 8 |
| 142 | False | 8 |
| 265 | False | 8 |
| 437 | False | 8 |
| 465 | False | 8 |
| 87 | True | 7 |
| 88 | True | 7 |
| 116 | False | 7 |
| 125 | False | 7 |
| 327 | False | 7 |
| 332 | False | 7 |
| 387 | False | 7 |
| 416 | False | 7 |
| 436 | False | 7 |

## 8. Auxiliary crossing angle statistics
Minimum angle: 15.203604093 degrees.
Mean angle: 60.033012438 degrees.
954 angle occurrences (three per detected triplet), including repeated physical intersections if they participate in different triplets. This is triplet-occurrence-weighted, not a unique-crossing angle distribution.
48 detected triplets contain at least one crossing below 20 degrees. The 20-degree marker is descriptive background only, not a new routing constraint. No crossing loss was calculated.

## 9. Boundary audit
| Triplet | Side lengths mm | Short count | Boundary side count |
| --- | --- | ---: | ---: |
| [3, 101, 301] | [0.21451845331818825, 0.125, 0.17433636113567275] | 0 | 1 |
| [78, 92, 145] | [0.21451845331818825, 0.17433636113567275, 0.125] | 0 | 1 |

## 10. Tests and validation
20 new test functions cover two-short detection, one-short/all-safe rejection, missing edges, eligibility, multiple-cross outside classification, spacing versus pitch, equality/near-threshold boundaries, canonical order, exactly-once enumeration, complete and sparse graph checks against small brute-force references, nonmutation, composition, empty inputs, multiplicity, boundary plus two shorts, non-cross filtering and invalid configuration.
All 337/337 tests passed, 0 warnings: original 317 plus 20 new tests. Test functions executed directly with the existing project Python; no pytest/networkx or other dependency installed.
Saved detected JSONL independently checked: 318 records, 318 unique canonical triplets, and every record meets at least two sides < 0.125-1e-9 using an independent hypot calculation. Summary accounting identities and composition/burden sums passed.
SHA-256 comparison confirmed all pre-existing src and output files unchanged. Input physical events hash:
af7e4edffc63e9f1193449494c834f73666ad5b15830a9de9d6185ea3a2e3eb8

## 11. Performance
| Stage | Seconds |
| --- | ---: |
| pair_map_seconds | 0.102294 |
| graph_seconds | 0.009834 |
| triangle_enumeration_seconds | 0.964859 |
| criterion_seconds | 9.847223 |
| total_seconds | 12.901945 |

One wall-clock run. Enumeration timing includes next()/set-intersection iteration; criterion timing includes canonicalization, eligibility and distances. Total also includes loading, hashing, aggregation and JSONL output, before final summary serialization. Stage totals need not equal total runtime. No parallelism, GPU or graph library.

## 12. Files and reproduction
- src/multi_crossing.py
- tests/test_multi_crossing.py
- scripts/analyze_legacy_512_multi_crossing_v01.py
- outputs/step_8_5_legacy_512_multi_crossing_summary.json
- outputs/step_8_5_legacy_512_multi_crossings.jsonl
All 318 detected triplets are saved (no truncation), with points, lengths, short count, spacing, classification, composition and auxiliary angles. The script caps optional detailed output at 100,000 records for future much larger results; counts always cover the entire graph.
Outside-assumption triplets are counted exhaustively; only 20 deterministic examples and their pair multiplicities are stored. Boundary examples are also retained. Millions of non-multi records are not dumped.
Run from project root: .venv\Scripts\python.exe -B -m scripts.analyze_legacy_512_multi_crossing_v01.

## 13. Conclusions and limits
318 eligible triplets meet the supplied legacy multi-waveguide criterion; 2 are boundary cases. 841,477 candidates lie outside the single-cross-per-pair assumption, so the reported 318 must not be read as an exhaustive generalized multi-intersection hazard count.
The 6,433 multi-cross pairs and detected clustered triplets provide future investigation priorities. This stage does not resolve them, change track allocation or move special-Z geometry.
This is a centerline crossing-point distance criterion, NOT finite-width envelope collision, fabrication clearance proof or physical spacing validation. It does not compute crossing loss or validate complete optical loss.
No K backtracking, hierarchy constraints, fragment optimization, rerouting, 3D, 1024, GUI or GDS was implemented. Stop at Step 8.5-G.
