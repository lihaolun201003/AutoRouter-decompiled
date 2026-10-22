# phase5 independent 3D verification

- verdict: **PASS**
- generated: 2026-10-23T00:03:19 (runtime 14.05 s)
- failed checks: none
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
- PASS `phase5_before_is_phase4_B`
- PASS `phase5_input_hashes_match`
- PASS `phase5_crossing_strictly_decreased`
- PASS `phase5_summary_pairs_match`
- PASS `phase5_actions_monotone`
- PASS `phase5_actions_count`
- PASS `phase5_stage_records_consistent`
- PASS `phase5_checkpoint_consistent`
- PASS `phase5_input_hashes_all_match`

## Key numbers

```json
{
 "target": "C:\\Users\\lihao\\Desktop\\Graduation Project\\OpticalWaveguideRouter2D\\outputs\\manual_c4_new_connectivity\\phase5_dynamic_optimization",
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
  "routes_sha256": "02c46a54f6ec5b0c0451e7974d2f3f27f02d206d329c68bd5d7b4576dbf2e8fc",
  "summary_sha256": "ec624837ba21ec83893d0bdab6c76cb4f25d2d45bd8a4ff54aab4d5dadf20e9c",
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
  "lifted_routes": 220,
  "transitions": 440,
  "high_layers": {
   "5": 36,
   "2": 124,
   "3": 36,
   "4": 24
  },
  "stack_heights_mm": {
   "2": 1.0,
   "3": 1.5,
   "4": 2.0,
   "5": 2.5
  }
 },
 "phase5_after_files": {
  "routes_sha256": "dcf42e4e509ba6f8247e15515e548b007ac7dc286cc3ff3544574f64d00c1ee3",
  "summary_sha256": null,
  "summary_exists": false
 },
 "phase5_after_crossings": {
  "points_by_height": {
   "0.0": 16096,
   "0.5": 7416,
   "1.0": 36,
   "1.5": 36,
   "2.0": 0,
   "2.5": 12
  },
  "pairs_by_height": {
   "0.0": 15952,
   "0.5": 7328,
   "1.0": 36,
   "1.5": 32,
   "2.0": 0,
   "2.5": 8
  },
  "points_total": 23596,
  "unique_pairs": 23356
 },
 "phase5_after_crossing_baseline": {
  "expected": 42584,
  "reported_before": null,
  "after": 23356,
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
  "min_3d_clearance_mm": 0.083207287,
  "unique_ports_used": 2048,
  "status": "exploratory_only"
 },
 "phase5_summary": {
  "routed_before": 1024,
  "routed_after": 1024,
  "unique_crossing_pairs_before": 25308,
  "unique_crossing_pairs_after": 23356,
  "crossing_reduction": 1952,
  "single_group_reschedules": 4,
  "joint_reschedules": 1,
  "recovered_failed_groups": 8,
  "lifted_groups_after": 55,
  "transitions_after": 440,
  "length_delta_mm": 10.2475,
  "validation_status": "exploratory_only"
 }
}
```
