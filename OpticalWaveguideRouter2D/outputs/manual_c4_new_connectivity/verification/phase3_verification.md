# phase3 independent 3D verification

- verdict: **PASS**
- generated: 2026-10-22T23:52:57 (runtime 8.27 s)
- failed checks: none
- warnings: none

## Checks

- PASS `phase3_payload_and_identity`
- PASS `phase3_xyz_ports`
- PASS `phase3_xy_replay_and_layer_model`
- PASS `phase3_c4_rotations_3d`
- PASS `phase3_crossing_statistics`
- PASS `phase3_crossing_reduction`
- PASS `phase3_crossings_before`
- PASS `phase3_l3d_validator`
- PASS `phase3_validation_artifact`
- PASS `phase3_lift_plans_consistent`
- PASS `phase3_summary_consistency`
- PASS `phase3_checkpoint_consistency`
- PASS `phase3_step_checkpoints_present`

## Key numbers

```json
{
 "target": "C:\\Users\\lihao\\Desktop\\Graduation Project\\OpticalWaveguideRouter2D\\outputs\\manual_c4_new_connectivity\\phase3_initial_lift",
 "phase3_layout": {
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
 "phase3_files": {
  "routes_sha256": "235ca2886b648df85da65b152728ffa19263ba0364ab1c13ef9728848b44f729",
  "summary_sha256": "4b82120024c869ac1ce3f97df888e73a9fdaf76985a8ef18801812557ee825f6",
  "summary_exists": true
 },
 "phase3_crossings": {
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
 "phase3_crossing_baseline": {
  "expected": 42584,
  "reported_before": 42584,
  "after": 25308,
  "delta": 17276
 },
 "phase3_validation": {
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
 "phase3_lift_plans": {
  "lifted": 47,
  "rejected": 42,
  "reverted": 11
 }
}
```
