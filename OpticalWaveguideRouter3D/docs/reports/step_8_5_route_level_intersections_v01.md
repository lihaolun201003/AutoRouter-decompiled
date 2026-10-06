# Step 8.5-E.1: Physical route intersection consolidation V0.1

## Scope and new interfaces
New module: src/physical_intersections.py. Existing Line-Line, Line-Arc, Arc-Arc, point_on_arc_2d, geometry, allocator and model code remain unchanged.

- PhysicalRouteIntersection: canonical route IDs, point, kind, travel tangent_a/tangent_b, crossing_angle_rad, raw_event_count.
- consolidate_route_intersections_2d(a, b, events, tol=1e-9, angular_tol=1e-9): consolidate existing raw events.
- find_physical_route_intersections_2d(a, b, tol=1e-9, angular_tol=1e-9): obtain raw events through the existing API then consolidate.

## RAW SEGMENT EVENT versus PHYSICAL ROUTE INTERSECTION
Raw events retain segment-level semantics: a segment endpoint intersection is touch. Physical intersections are coordinate-consolidated separately within each unordered route pair, then classified using the complete route's local travel tangents.
Different route pairs at the same coordinate are never merged. Consequently physical point totals below are pair-local unique discrete intersections, NOT globally unique spatial locations across all waveguides.

## Grouping
Route IDs are canonicalized in ascending order; corresponding raw segment indices are swapped when necessary. Events from another pair are rejected.
Discrete events are sorted deterministically by x/y and segment indices. Each cluster requires every pair of member coordinates to be within Euclidean tol (complete-link grouping), preventing transitive tolerance chains from merging more distant points. The lexicographically first coordinate is copied as representative. The inputs and raw event list are not modified.
Overlap records retain kind=overlap and point=None individually. No interval union is implemented; overlap counts are preserved raw overlap relations, not unique maximal overlap intervals. Discrete contacts at overlap boundaries are not absorbed into overlaps.

## Tangents, smooth joins and classification
Line tangent is (end-start)/length. Arc tangent is the normalized radius rotated +90 degrees for CCW or -90 degrees for CW, following route travel.
Raw indices locate the route occurrence; neighboring segments at a join are also included, even if a numerical candidate appeared for only one segment. At endpoint proximity, tangent is evaluated at the exact segment endpoint. Incoming/outgoing travel tangents must agree. Consistency tolerance uses angular_tol plus tol/r for arc endpoint uncertainty; a non-smooth join or multiple nonadjacent route occurrences is rejected with ValueError rather than assigned a guessed tangent.
Interior physical point: abs(cross(unit_tangent_a,unit_tangent_b)) > angular_tol gives cross; parallel/antiparallel gives touch.
Actual route start/end contacts remain touch, including nonparallel endpoint contacts. This preserves the explicitly requested straight-route endpoint-touch test and distinguishes a complete route endpoint from an internal segment join.
Empty routes return no events. This layer requires raw events generated for the supplied current routes; it is not a validator for arbitrary externally fabricated event coordinates.

## Crossing angle
angle = atan2(abs(cross(tangent_a,tangent_b)), abs(dot(tangent_a,tangent_b))). Range is [0, pi/2]. Reversing either complete route reverses its travel tangent but leaves the angle unchanged. Tests verify 140 degrees becomes 40 degrees.
Length tolerance and dimensionless angular tolerance are explicit separate arguments, both defaulting to 1e-9. Tangents and angles are available for discrete events; overlap has neither a single point nor a single angle.
No crossing loss table or loss function is used.

## Real legacy 512 integration
Same Step E inputs and configuration: snapshot-restored positions, radius=5.0, A+G1+S1, unchanged midpoint special-Z. 454 assigned ordinary and 58 allocator-unsupported special-Z remain distinct; all 512 analytic geometries pass checks.
Every one of 130,816 unordered route pairs was recomputed using the unchanged raw API. Input hashes, waveguides, assignments and analytic routes were checked unchanged; raw events were checked unchanged after consolidation. No failures occurred.

| Level / group | Pairs checked | Cross points/events | Cross pairs | Touch points/events | Touch pairs | Overlap relations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| raw / global | 130816 | 55932 | 49499 | 12 | 3 | 0 |
| raw / ordinary-ordinary | 102831 | 47186 | 41094 | 0 | 0 | 0 |
| raw / ordinary-special | 26332 | 8706 | 8365 | 0 | 0 | 0 |
| raw / special-special | 1653 | 40 | 40 | 12 | 3 | 0 |
| physical / global | 130816 | 55935 | 49502 | 0 | 0 | 0 |
| physical / ordinary-ordinary | 102831 | 47186 | 41094 | 0 | 0 | 0 |
| physical / ordinary-special | 26332 | 8706 | 8365 | 0 | 0 | 0 |
| physical / special-special | 1653 | 43 | 43 | 0 | 0 | 0 |

Global physical_overlap_relations=0 and pairs_with_physical_overlap=0. Physical cross points=55,935, physical touch points=0; pairs_with_physical_cross=49,502 and pairs_with_physical_touch=0.

## Three special-Z midpoint pairs: measured tangent evidence
| Pair | Point | tangent A | tangent B | abs cross | Angle rad / degrees | Classification | Raw members |
| --- | --- | --- | --- | ---: | --- | --- | ---: |
| 20 / 257 | (135.775000, 75.000000) | (-0.942218128, 0.335000000) | (-0.600000000, -0.800000000) | 0.954774502 | 1.268900448 / 72.702640 | cross | 4 |
| 22 / 259 | (140.450000, 75.000000) | (0.600000000, 0.800000000) | (0.942218128, -0.335000000) | 0.954774502 | 1.268900448 / 72.702640 | cross | 4 |
| 224 / 466 | (76.750000, 75.000000) | (0.644030279, 0.765000000) | (0.929031754, -0.370000000) | 0.949000495 | 1.250050351 / 71.622609 | cross | 4 |

All three are internal route crossings, not physical tangencies. Each raw group has four segment-endpoint touches at the Arc1/Arc2 joins. All three consolidate to one cross each; no underlying raw classification was changed.

## Raw versus physical differences
Raw cross coordinate-only consolidation: 55,932 clusters from 55,932 raw cross events; duplicate raw cross events removed = 0. This was measured across all pairs, not assumed.
Raw touch: 12 events -> 3 pair-local coordinates -> 3 physical cross points.
Physical cross minus raw cross = +3 (55,935 - 55,932). Physical cross pairs minus raw cross pairs = +3 (49,502 - 49,499). Physical touch = 0.
Total discrete raw events 55,944 -> total physical discrete points 55,935: nine repeated segment-event records removed, with the remaining three contact points reclassified.

## Tests
19 new direct test functions cover straight crossing/endpoints, Line-Arc and Arc-Arc joins, four-touch consolidation, true tangency and antiparallel tangency, reversal, acute angle, input nonmutation, unordered pair symmetry, different pairs at the same point, overlap, nonsmooth rejection, empty inputs, invalid tolerance, two distinct points, coordinate tolerance and nontransitive clustering.
All 300 test functions passed: models 18, geometry 63, router_2d 48, collision 98, loss 26, io 28, physical_intersections 19. Warnings: 0. Existing 281 tests remain unchanged and pass. No dependencies installed.

## Runtime and saved artifacts
Observed pair loop runtime: 24.609 s; total integration: 24.924 s before final JSON serialization. Includes raw detection, physical consolidation, a cross-only duplicate diagnostic pass, counts, and event JSONL output. Single wall-clock measurement, no parallel/index optimization.

- scripts/validate_legacy_512_physical_intersections.py
- outputs/step_8_5_legacy_512_physical_summary.json
- outputs/step_8_5_legacy_512_physical_events.jsonl (55,935 discrete events, each including tangents and angle)
- tests/test_physical_intersections.py

Re-run from project root:
` .venv\Scripts\python.exe -B -m scripts.validate_legacy_512_physical_intersections <fiberBoard512.xlsx> <fiberBoard0data.xlsx> `

Input paths and SHA-256:
- C:\Users\lihao\Desktop\Graduation Project\自动排布\AutoRouter\fiberBoard512.xlsx
  SHA-256: 71a19ec1739de75453608d1d9bd0bb2b9ad102140e4af5057c12e60c0accd7ff
- C:\Users\lihao\Desktop\Graduation Project\自动排布\AutoRouter\fiberBoard0data.xlsx
  SHA-256: 6901bd1f15388cf15831b57297be9a6a6f51ef1d661196e282dc5f1bbd6a8770

## Limitations and stop boundary
Unique smooth tangents are required. Non-smooth corner topology, multiple visits to the same point and full overlap interval unions are not implemented. Closed-route seam topology has no special treatment. Near-parallel relations remain tolerance-based; there is no arbitrary-precision guarantee.
No finite width, clearance, loss, routing modification, placement optimization or 3D is implemented. The 55,935 physical cross points do not represent collision-free routing or a loss estimate.
Step 8.5-E.1 is complete. Step 8.5-F was not started.
