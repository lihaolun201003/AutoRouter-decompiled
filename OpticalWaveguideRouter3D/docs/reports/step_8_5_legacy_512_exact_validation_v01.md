# Step 8.5-E: legacy 512 exact curve global validation V0.1

## 1. Scope and reproducibility
Read-only source loading and calls to the existing geometry, allocator and collision APIs. No business module was modified. No dependencies were installed. A+G1+S1 and special-Z midpoint placement are unchanged.

Run from project root with the existing environment:
` .venv\Scripts\python.exe -B -m scripts.validate_legacy_512_exact <fiberBoard512.xlsx> <fiberBoard0data.xlsx> `

Inputs (SHA-256 checked unchanged after validation):
- C:\Users\lihao\Desktop\Graduation Project\自动排布\AutoRouter\fiberBoard512.xlsx
  SHA-256: `71a19ec1739de75453608d1d9bd0bb2b9ad102140e4af5057c12e60c0accd7ff`
- C:\Users\lihao\Desktop\Graduation Project\自动排布\AutoRouter\fiberBoard0data.xlsx
  SHA-256: `6901bd1f15388cf15831b57297be9a6a6f51ef1d661196e282dc5f1bbd6a8770`

## 2. Geometry construction and individual validation
allocator_assigned = 454; allocator_unsupported_special_z = 58; analytic_geometry_available = 512.
All 512 waveguide IDs are unique and exactly cover the input. All 512 geometries pass validation, exact start/end preservation in original input direction, segment continuity, radius=5.0 consistency, unit travel tangent continuity (1e-9), and finite positive total length. Invalid geometry: 0; construction/validation exceptions: 0.

Ordinary skeletons use smooth_orthogonal_route_2d. The 58 unsupported connections use the existing restricted double-arc constructor independently; their allocator status and unassigned track fields remain unchanged. Geometry availability is not allocator assignment success.

Configuration: board_height=150, waveguide_width=0.05, spacing=0.125, bend_radius=5.0, tol=1e-9. Units follow the legacy snapshot mm interpretation. Width/spacing are existing allocator inputs, NOT physical envelope collision checks.

## 3. Self-intersection
512 routes checked: self_cross=0, self_touch=0, self_overlap=0. Normal shared adjacent endpoints are ignored by the existing API. No route IDs or reasons need listing because no failures occurred.

## 4. Complete global pair validation
All 512*511/2 = 130,816 unordered route pairs were checked by find_smoothed_route_intersections_2d. Failed pair calls: 0. Pairs with any event: 49,502.

| Group | Pairs checked | Cross events | Cross pairs | Touch events | Touch pairs | Overlap events | Overlap pairs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| global | 130816 | 55932 | 49499 | 12 | 3 | 0 | 0 |
| ordinary-ordinary | 102831 | 47186 | 41094 | 0 | 0 | 0 | 0 |
| ordinary-special | 26332 | 8706 | 8365 | 0 | 0 | 0 | 0 |
| special-special | 1653 | 40 | 40 | 12 | 3 | 0 | 0 |

## 5. Ordinary 454: curve versus skeleton
The ordinary-only 102,831 pairs were separately recomputed, rather than only extracted from global counters. Their results exactly equal the ordinary-ordinary subset.

| Metric | Prior skeleton baseline | Current curves | Difference |
| --- | ---: | ---: | ---: |
| Cross raw events | 47,292 | 47,186 | -106 |
| Pairs with cross | 41,147 | 41,094 | -53 |
| Touch events | 0 | 0 | 0 |
| Overlap events | 0 | 0 | 0 |

Skeleton values are the previously established baseline supplied for this task; the skeleton pass was not re-executed. Rounding changes the centerline near corners. These are aggregate differences, not a claim that exactly 106 original physical crossings disappeared or that no new crossing appeared. The detector was not changed to force agreement.

## 6. Special-Z analysis and midpoint contacts
56 of 58 special-Z routes have at least one cross with another route. IDs 278 and 279 have zero cross events. Ordinary-special interactions produce 8,706 cross events across 8,365 route pairs; special-special produces 40 cross events across 40 route pairs. This is a substantial interaction burden, not a collision-free result.

All 12 raw touch events occur at special-Z arc joins:

| Route IDs | Representative coordinate | Raw touch events |
| --- | --- | ---: |
| 20 / 257 | (135.775, 75.0) | 4 |
| 22 / 259 | (140.45, 75.0) | 4 |
| 224 / 466 | (76.75, 75.0) | 4 |

Each pair contributes the four combinations of arc indices 1 and 2. Coordinates within each group agree within 1e-9. These are three route-pair contact locations, not twelve distinct physical points. The API classifies arc-endpoint intersections as touch; this does not independently establish that the full smooth routes are tangent rather than transversely meeting at their internal joins. Route-level topology classification across joins remains a possible later refinement. Current raw classifications are preserved.

## 7. Per-waveguide burden
Full per-waveguide cross-event, cross-pair, touch-event and overlap-event counts are saved in the summary JSON. Cross burden top ten, ordered by events descending then ID:

| Waveguide ID | Type | Cross events | Cross pairs | Touch events | Overlap events |
| --- | --- | ---: | ---: | ---: | ---: |
| 34 | ordinary | 473 | 370 | 0 | 0 |
| 177 | ordinary | 446 | 357 | 0 | 0 |
| 290 | ordinary | 409 | 315 | 0 | 0 |
| 265 | ordinary | 406 | 323 | 0 | 0 |
| 9 | ordinary | 378 | 304 | 0 | 0 |
| 345 | ordinary | 364 | 291 | 0 | 0 |
| 35 | ordinary | 353 | 288 | 0 | 0 |
| 291 | ordinary | 353 | 282 | 0 | 0 |
| 433 | ordinary | 352 | 283 | 0 | 0 |
| 185 | ordinary | 349 | 294 | 0 | 0 |

## 8. Counting semantics and saved artifacts
Event counts are raw segment-pair events, NOT unique physical crossing counts. A route pair may have multiple events; category pair counts need not be mutually exclusive in general. No global coordinate deduplication was applied. Per-waveguide incident totals count each event/pair at both endpoints; the cross sums were independently checked against twice the global values.

- scripts/validate_legacy_512_exact.py: deterministic integration validator.
- outputs/step_8_5_legacy_512_exact_summary.json: config, input hashes, checks, groups, timing, full per-waveguide burden and top ten.
- outputs/step_8_5_legacy_512_exact_events.jsonl: all 55,944 raw pair events, including route IDs, segment indices/types, kind and coordinates.

## 9. Runtime
Global 130,816-pair loop: 19.022 s. Includes event aggregation and JSONL writes.
Separate ordinary-only pass: 14.108 s.
Total integration measurement: 33.507 s, before final summary serialization.
Single observed wall-clock timings using perf_counter, not a benchmark average. The existing brute-force implementation completed within a reasonable experiment duration; no spatial indexing, parallelization or numerical detector changes were needed.

## 10. Tests and invariants
Existing unit tests: models 18, geometry 63, router_2d 48, collision 98, loss 26, io 28; total 281/281 passed by direct test-function execution, 0 warnings.
Added one deterministic real-data integration script with ten final checks; all passed. These ten assertions are not counted as ten additional unit tests.

- ordinary_454: True
- special_58: True
- total_512: True
- unique_ids: True
- id_coverage: True
- geometry_all_valid: True
- full_pairs: True
- collision_completed: True
- inputs_unchanged: True
- allocator_unchanged: True

Endpoint, radius, tangent and finite-length assertions run for every route. Deep-copy equality confirms waveguides, preparations, assignments, skeletons and analytic geometry remain unchanged by validation. Input source file hashes are unchanged.

## 11. Conclusions and next-stage questions
All 512/512 connections have valid analytic Line/Arc geometry. This does NOT mean 512 connections are routed without conflicts: 55,932 raw cross events and 12 raw touch events exist. Overlap is zero under the current zero-width analytic detector and tolerance.

Future work needs to decide how to address the measured interaction burden, shared special-Z midpoint contacts and the separation between analytic availability and allocator unsupported status. Finite width, clearance and optical loss remain unassessed. No next-stage optimization, reassignment, rerouting, 3D or Step 8.5-F work was performed.
Optional visualization was omitted; all acceptance statistics and raw events are retained.
