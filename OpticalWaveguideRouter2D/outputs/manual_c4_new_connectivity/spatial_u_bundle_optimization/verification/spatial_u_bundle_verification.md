# 空间分组式 U 形线束三维布线：独立验收报告

- 结论：**PASS**
- 生成时间：2026-10-23T11:06:56
- 验收器：independent: own geometry/C4/metrics; frozen lift_cross.validate_payload_v4 (v4_root=phase2_2d) for the authoritative 3D pass

## 检查项（23/23 PASS）

| 检查 | 结果 | 说明 |
|---|---|---|
| u_only_payload_contract | PASS | [] |
| u_only_identity | PASS | [] |
| final_payload_contract | PASS | [] |
| final_identity | PASS | [] |
| u_only_route_geometry | PASS | [] |
| final_route_geometry | PASS | [] |
| u_only_target_quartets | PASS | {"target": 64, "reached": 63, "failed": [167], "problems": [{"group_id": 167, "target_layer": 3, "rebuilt": false, "errors": [[551, "high_layer", 4, 3], [551, "high_layer_z", 2.0, 1.5], [551, "layer_sequence", [1, 4, 1]] |
| u_only_c4_rotation_symmetry | PASS | [] |
| final_target_quartets | PASS | {"target": 64, "reached": 64, "failed": [], "problems": [], "details": {"20": {"rebuilt": true, "ok": true, "target_layer": 2, "errors": []}, "21": {"rebuilt": true, "ok": true, "target_layer": 2, "errors": []}, "22": {" |
| final_c4_rotation_symmetry | PASS | [] |
| u_only_v2_invariance | PASS | {"non_target": 768, "changed": []} |
| final_v2_invariance | PASS | {"non_target": 764, "changed": []} |
| final_moved_group11 | PASS | {"expected_group": 11, "route_ids": [12, 29, 231, 232], "report": [{"route_id": 12, "identity_unchanged": true, "ports_unchanged": true, "layer_before": [1, 3, 1], "layer_after": [1, 5, 1], "z_before": [0.0, 1.5, 0.0], " |
| final_moved_group11_geometry | PASS | {"note": "each flat part must be one continuous sub-chain; a gap equal to an old transition footprint indicates the 2D chain was assembled from flattened parts of the already-lifted route", "findings": [{"route_id": 12,  |
| baseline_l3d_validator | PASS | {"errors": [], "group_hits": {}} |
| u_only_l3d_validator | PASS | {"errors": [], "group_hits": {}} |
| final_l3d_validator | PASS | {"errors": [], "group_hits": {}} |
| final_metrics_match_production | PASS | [] |
| comparison_table_match | PASS | [] |
| u_layer_assignment | PASS | [] |
| validation_artifact | PASS | [] |
| figures | PASS | {"figure_stems_expected": 12, "present_stems": 12, "missing": [], "summary_figures": "C:\\Users\\lihao\\Desktop\\Graduation Project\\OpticalWaveguideRouter2D\\outputs\\manual_c4_new_connectivity\\spatial_u_bundle_optimiz |
| products_stable_during_run | PASS | [] |

## 关键数字

| 指标 | 基线 V2 | u_only | final |
|---|---:|---:|---:|
| 布通 | 1024 | 1024 | 1024 |
| 唯一交叉对（跨高度去重） | 23356 | 12408 | 12824 |
| 同层 U-U 交叉对 | 104 | 0 | 0 |
| 升降次数 | 440 | 824 | 824 |
| 三维总长度 mm | 97495.7612 | 98635.0733 | 98539.0127 |
| 最小三维净空 mm | 0.083207287 | 0.083207287 | 0.083207287 |
| 最小曲率半径 mm | 14.999999965 | 14.999999961 | 14.999999961 |
| 目标四元组达标 | 0 | 63 | 64 |

- u_only 目标四元组：63/64，失败 [167]
- final 目标四元组：64/64，失败 []
- u_only 失败组 [167]：生产 run.log 记录 'u_only: group ... FAILED'（final 通过 group 11 的 L3→L5 局部重路由后达到 64/64）
- u_only 独立三维验收：status=exploratory_only，exploratory_pass=True，formal_acceptance=False，counts={'violations': 0, 'contract_errors': 0, 'port_errors': 0, 'geometry_errors': 0, 'curvature_violations': 0, 'clearance_violations': 0, 'same_plane_violations': 0, 'self_clearance_violations': 0, 'other_errors': 0}
- final 独立三维验收：status=exploratory_only，exploratory_pass=True，formal_acceptance=False，counts={'violations': 0, 'contract_errors': 0, 'port_errors': 0, 'geometry_errors': 0, 'curvature_violations': 0, 'clearance_violations': 0, 'same_plane_violations': 0, 'self_clearance_violations': 0, 'other_errors': 0}
- 唯一交叉对：baseline 23356 → u_only 12408 → final 12824（final 相对基线 -10532）
- final 各层水平波导数（有该层 flat 的路线数）：L1-z1=512, L1-z2=512, L2=252, L3=80, L4=68, L5=12

## 与生产数字的差异

- 无（独立重算与 summary/comparison_table 一致）

> 说明：层高为探索性仿真参数（unconfirmed_simulation），几何 PASS 不等于制造工艺正式验收；本报告为独立重算。
