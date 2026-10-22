# phase4 independent 3D verification

- verdict: **PASS**
- generated: 2026-10-22T23:53:28 (runtime 31.7 s)
- failed checks: none
- warnings: none

## Checks

- PASS `A_0.25mm_payload_and_identity`
- PASS `A_0.25mm_xyz_ports`
- PASS `A_0.25mm_xy_replay_and_layer_model`
- PASS `A_0.25mm_c4_rotations_3d`
- PASS `A_0.25mm_crossing_statistics`
- PASS `A_0.25mm_crossing_reduction`
- PASS `A_0.25mm_crossings_before`
- PASS `A_0.25mm_l3d_validator`
- PASS `A_0.25mm_validation_artifact`
- PASS `A_0.25mm_lift_plans_consistent`
- PASS `B_0.50mm_payload_and_identity`
- PASS `B_0.50mm_xyz_ports`
- PASS `B_0.50mm_xy_replay_and_layer_model`
- PASS `B_0.50mm_c4_rotations_3d`
- PASS `B_0.50mm_crossing_statistics`
- PASS `B_0.50mm_crossing_reduction`
- PASS `B_0.50mm_crossings_before`
- PASS `B_0.50mm_l3d_validator`
- PASS `B_0.50mm_validation_artifact`
- PASS `B_0.50mm_lift_plans_consistent`
- PASS `C_0.75mm_payload_and_identity`
- PASS `C_0.75mm_xyz_ports`
- PASS `C_0.75mm_xy_replay_and_layer_model`
- PASS `C_0.75mm_c4_rotations_3d`
- PASS `C_0.75mm_crossing_statistics`
- PASS `C_0.75mm_crossing_reduction`
- PASS `C_0.75mm_crossings_before`
- PASS `C_0.75mm_l3d_validator`
- PASS `C_0.75mm_validation_artifact`
- PASS `C_0.75mm_lift_plans_consistent`
- PASS `D_1.00mm_payload_and_identity`
- PASS `D_1.00mm_xyz_ports`
- PASS `D_1.00mm_xy_replay_and_layer_model`
- PASS `D_1.00mm_c4_rotations_3d`
- PASS `D_1.00mm_crossing_statistics`
- PASS `D_1.00mm_crossing_reduction`
- PASS `D_1.00mm_crossings_before`
- PASS `D_1.00mm_l3d_validator`
- PASS `D_1.00mm_validation_artifact`
- PASS `D_1.00mm_lift_plans_consistent`
- PASS `phase4_cross_config_invariance`
- PASS `ablation_table_consistency`
- PASS `phase4_shared_baseline`

## Key numbers

```json
{
 "target": "C:\\Users\\lihao\\Desktop\\Graduation Project\\OpticalWaveguideRouter2D\\outputs\\manual_c4_new_connectivity\\phase4_ablation",
 "config_A_0.25mm": {
  "dir": "C:\\Users\\lihao\\Desktop\\Graduation Project\\OpticalWaveguideRouter2D\\outputs\\manual_c4_new_connectivity\\phase4_ablation\\A_0.25mm",
  "expected_heights": [
   0.75,
   1.0,
   1.25,
   1.5
  ]
 },
 "A_0.25mm_layout": {
  "records": 1024,
  "routed": 1024,
  "failed": 0,
  "lifted_routes": 288,
  "transitions": 576,
  "high_layers": {
   "3": 76,
   "2": 92,
   "4": 52,
   "5": 68
  },
  "stack_heights_mm": {
   "2": 0.75,
   "3": 1.0,
   "4": 1.25,
   "5": 1.5
  }
 },
 "A_0.25mm_files": {
  "routes_sha256": "bb4cc34d030a1b5cee49bbbafbc066cedfeea87093ffa7be9f4588092d68aed7",
  "summary_sha256": "07c4ee44e4a7d8166e44ecef6e8df3e49fb3a30d4a6b59d05422cf9c8f34ac6d",
  "summary_exists": true
 },
 "A_0.25mm_crossings": {
  "points_by_height": {
   "0.0": 17728,
   "0.5": 2500,
   "0.75": 188,
   "1.0": 188,
   "1.25": 36,
   "1.5": 160
  },
  "pairs_by_height": {
   "0.0": 17564,
   "0.5": 2412,
   "0.75": 124,
   "1.0": 172,
   "1.25": 20,
   "1.5": 124
  },
  "points_total": 20800,
  "unique_pairs": 20416
 },
 "A_0.25mm_crossing_baseline": {
  "expected": 42584,
  "reported_before": 42584,
  "after": 20416,
  "delta": 22168
 },
 "A_0.25mm_validation": {
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
  "min_3d_clearance_mm": 0.081609912,
  "unique_ports_used": 2048,
  "status": "exploratory_only"
 },
 "A_0.25mm_lift_plans": {
  "lifted": 72,
  "rejected": 69,
  "reverted": 3
 },
 "config_B_0.50mm": {
  "dir": "C:\\Users\\lihao\\Desktop\\Graduation Project\\OpticalWaveguideRouter2D\\outputs\\manual_c4_new_connectivity\\phase4_ablation\\B_0.50mm",
  "expected_heights": [
   1.0,
   1.5,
   2.0,
   2.5
  ]
 },
 "B_0.50mm_layout": {
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
 "B_0.50mm_files": {
  "routes_sha256": "02c46a54f6ec5b0c0451e7974d2f3f27f02d206d329c68bd5d7b4576dbf2e8fc",
  "summary_sha256": "ec624837ba21ec83893d0bdab6c76cb4f25d2d45bd8a4ff54aab4d5dadf20e9c",
  "summary_exists": true
 },
 "B_0.50mm_crossings": {
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
 "B_0.50mm_crossing_baseline": {
  "expected": 42584,
  "reported_before": 42584,
  "after": 25308,
  "delta": 17276
 },
 "B_0.50mm_validation": {
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
 "B_0.50mm_lift_plans": {
  "lifted": 47,
  "rejected": 42,
  "reverted": 11
 },
 "config_C_0.75mm": {
  "dir": "C:\\Users\\lihao\\Desktop\\Graduation Project\\OpticalWaveguideRouter2D\\outputs\\manual_c4_new_connectivity\\phase4_ablation\\C_0.75mm",
  "expected_heights": [
   1.25,
   2.0,
   2.75,
   3.5
  ]
 },
 "C_0.75mm_layout": {
  "records": 1024,
  "routed": 1024,
  "failed": 0,
  "lifted_routes": 268,
  "transitions": 536,
  "high_layers": {
   "3": 52,
   "2": 124,
   "5": 48,
   "4": 44
  },
  "stack_heights_mm": {
   "2": 1.25,
   "3": 2.0,
   "4": 2.75,
   "5": 3.5
  }
 },
 "C_0.75mm_files": {
  "routes_sha256": "95117fc5692893081e4ad54ab61a51161bc56a0cf38c3634b6b762c204c1474f",
  "summary_sha256": "f7055d40a9dbfc86981fa01e439a55c929083901bb34db00b82be1edd13e91b2",
  "summary_exists": true
 },
 "C_0.75mm_crossings": {
  "points_by_height": {
   "0.0": 15792,
   "0.5": 5296,
   "1.25": 48,
   "2.0": 44,
   "2.75": 40,
   "3.5": 28
  },
  "pairs_by_height": {
   "0.0": 15648,
   "0.5": 5016,
   "1.25": 48,
   "2.0": 40,
   "2.75": 40,
   "3.5": 28
  },
  "points_total": 21248,
  "unique_pairs": 20820
 },
 "C_0.75mm_crossing_baseline": {
  "expected": 42584,
  "reported_before": 42584,
  "after": 20820,
  "delta": 21764
 },
 "C_0.75mm_validation": {
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
  "min_3d_clearance_mm": 0.091518627,
  "unique_ports_used": 2048,
  "status": "exploratory_only"
 },
 "C_0.75mm_lift_plans": {
  "lifted": 67,
  "rejected": 69,
  "reverted": 5
 },
 "config_D_1.00mm": {
  "dir": "C:\\Users\\lihao\\Desktop\\Graduation Project\\OpticalWaveguideRouter2D\\outputs\\manual_c4_new_connectivity\\phase4_ablation\\D_1.00mm",
  "expected_heights": [
   1.5,
   2.5,
   3.5,
   4.5
  ]
 },
 "D_1.00mm_layout": {
  "records": 1024,
  "routed": 1024,
  "failed": 0,
  "lifted_routes": 264,
  "transitions": 528,
  "high_layers": {
   "3": 56,
   "2": 104,
   "4": 84,
   "5": 20
  },
  "stack_heights_mm": {
   "2": 1.5,
   "3": 2.5,
   "4": 3.5,
   "5": 4.5
  }
 },
 "D_1.00mm_files": {
  "routes_sha256": "ac5ac7d95855f7791ff4d201d84479026e27bf2e8c08ce2525d27f586178c41e",
  "summary_sha256": "3f5ea54948c47bca0cdf733e4e27f6100afc5dde4e5d505ab45cb1313fab9afa",
  "summary_exists": true
 },
 "D_1.00mm_crossings": {
  "points_by_height": {
   "0.0": 16880,
   "0.5": 4716,
   "1.5": 40,
   "2.5": 52,
   "3.5": 32,
   "4.5": 12
  },
  "pairs_by_height": {
   "0.0": 16740,
   "0.5": 4532,
   "1.5": 36,
   "2.5": 44,
   "3.5": 28,
   "4.5": 12
  },
  "points_total": 21732,
  "unique_pairs": 21392
 },
 "D_1.00mm_crossing_baseline": {
  "expected": 42584,
  "reported_before": 42584,
  "after": 21392,
  "delta": 21192
 },
 "D_1.00mm_validation": {
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
  "min_3d_clearance_mm": 0.082167281,
  "unique_ports_used": 2048,
  "status": "exploratory_only"
 },
 "D_1.00mm_lift_plans": {
  "lifted": 66,
  "rejected": 72,
  "reverted": 3
 },
 "phase4_cross_config": {
  "configs": [
   "A_0.25mm",
   "B_0.50mm",
   "C_0.75mm",
   "D_1.00mm"
  ],
  "routes_with_identical_xy": 1024,
  "quartet_partition_identical": true
 }
}
```
