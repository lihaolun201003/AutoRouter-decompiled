# phase5 independent 3D verification

- verdict: **FAIL**
- generated: 2026-10-22T23:35:54 (runtime 16.38 s)
- failed checks: ['phase5_before_is_phase4_B', 'phase5_crossing_strictly_decreased', 'phase5_checkpoint_consistent']
- warnings: ['phase5_before: crossings_before.json missing', 'phase5_after: crossings_before.json missing']

## Checks

- PASS `phase5_before_payload_and_identity`
- PASS `phase5_before_xyz_ports`
- PASS `phase5_before_xy_replay_and_layer_model`
- PASS `phase5_before_c4_rotations_3d`
- PASS `phase5_before_crossing_statistics`
- PASS `phase5_before_crossing_reduction`
- PASS `phase5_before_l3d_validator`
- PASS `phase5_before_validation_artifact`
- PASS `phase5_before_lift_plans_consistent`
- PASS `phase5_after_payload_and_identity`
- PASS `phase5_after_xyz_ports`
- PASS `phase5_after_xy_replay_and_layer_model`
- PASS `phase5_after_c4_rotations_3d`
- PASS `phase5_after_crossing_statistics`
- PASS `phase5_after_l3d_validator`
- PASS `phase5_after_validation_artifact`
- PASS `phase5_summary_routed_after`
- PASS `phase5_summary_routed_before`
- PASS `phase5_summary_crossing_counts`
- FAIL `phase5_before_is_phase4_B`
- FAIL `phase5_crossing_strictly_decreased`
- PASS `phase5_summary_pairs_match`
- PASS `phase5_actions_monotone`
- PASS `phase5_actions_count`
- PASS `phase5_stage_records_consistent`
- FAIL `phase5_checkpoint_consistent`

## Key numbers

```json
{
 "target": "C:\\Users\\lihao\\Desktop\\Graduation Project\\OpticalWaveguideRouter2D\\outputs\\manual_c4_new_connectivity\\verification\\_selftest_phase5",
 "phase5_before_layout": {
  "records": 1024,
  "routed": 1024,
  "failed": 0,
  "lifted_routes": 188,
  "transitions": 376,
  "high_layers": {
   "2": 104,
   "4": 24,
   "3": 32,
   "5": 28
  },
  "stack_heights_mm": {
   "2": 1.0,
   "3": 1.5,
   "4": 2.0,
   "5": 2.5
  }
 },
 "phase5_before_files": {
  "routes_sha256": "235ca2886b648df85da65b152728ffa19263ba0364ab1c13ef9728848b44f729",
  "summary_sha256": "4b82120024c869ac1ce3f97df888e73a9fdaf76985a8ef18801812557ee825f6",
  "summary_exists": true
 },
 "phase5_before_crossings": {
  "points_by_height": {
   "0.0": 18096,
   "0.5": 7416,
   "1.0": 20,
   "1.5": 24,
   "2.0": 0,
   "2.5": 8
  },
  "pairs_by_height": {
   "0.0": 17936,
   "0.5": 7328,
   "1.0": 20,
   "1.5": 20,
   "2.0": 0,
   "2.5": 4
  },
  "points_total": 25564,
  "unique_pairs": 25308
 },
 "phase5_before_crossing_baseline": {
  "expected": 42584,
  "reported_before": 42584,
  "after": 25308,
  "delta": 17276
 },
 "phase5_before_validation": {
  "passed": true,
  "counts": {
   "violations": 0,
   "contract_errors": 0,
   "port_errors": 0,
   "geometry_errors": 0,
   "curvature_violations": 0,
   "clearance_violations": 0,
   "same_plane_violations": 0,
   "self_clearance_violations": 0,
   "other_errors": 0
  },
  "min_curvature_radius_mm": 14.999999965,
  "min_3d_clearance_mm": 0.086214914,
  "unique_ports_used": 2048,
  "status": "exploratory_only"
 },
 "phase5_before_lift_plans": {
  "lifted": 47,
  "rejected": 42,
  "reverted": 11
 },
 "phase5_after_layout": {
  "records": 1024,
  "routed": 1024,
  "failed": 0,
  "lifted_routes": 188,
  "transitions": 376,
  "high_layers": {
   "2": 104,
   "4": 24,
   "3": 32,
   "5": 28
  },
  "stack_heights_mm": {
   "2": 1.0,
   "3": 1.5,
   "4": 2.0,
   "5": 2.5
  }
 },
 "phase5_after_files": {
  "routes_sha256": "235ca2886b648df85da65b152728ffa19263ba0364ab1c13ef9728848b44f729",
  "summary_sha256": null,
  "summary_exists": false
 },
 "phase5_after_crossings": {
  "points_by_height": {
   "0.0": 18096,
   "0.5": 7416,
   "1.0": 20,
   "1.5": 24,
   "2.0": 0,
   "2.5": 8
  },
  "pairs_by_height": {
   "0.0": 17936,
   "0.5": 7328,
   "1.0": 20,
   "1.5": 20,
   "2.0": 0,
   "2.5": 4
  },
  "points_total": 25564,
  "unique_pairs": 25308
 },
 "phase5_after_crossing_baseline": {
  "expected": 42584,
  "reported_before": null,
  "after": 25308,
  "delta": null
 },
 "phase5_after_validation": {
  "passed": true,
  "counts": {
   "violations": 0,
   "contract_errors": 0,
   "port_errors": 0,
   "geometry_errors": 0,
   "curvature_violations": 0,
   "clearance_violations": 0,
   "same_plane_violations": 0,
   "self_clearance_violations": 0,
   "other_errors": 0
  },
  "min_curvature_radius_mm": 14.999999965,
  "min_3d_clearance_mm": 0.086214914,
  "unique_ports_used": 2048,
  "status": "exploratory_only"
 },
 "phase5_summary": {
  "routed_before": 1024,
  "routed_after": 1024,
  "unique_crossing_pairs_before": 25308,
  "unique_crossing_pairs_after": 25308,
  "crossing_reduction": 0,
  "single_group_reschedules": 0,
  "joint_reschedules": 0,
  "recovered_failed_groups": 0,
  "lifted_groups_after": 47,
  "transitions_after": 376,
  "length_delta_mm": 0,
  "validation_status": "exploratory_only"
 }
}
```
