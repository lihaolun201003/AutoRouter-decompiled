# 结构化分层布线 A/B 独立几何验收报告

- 结论：**FAIL**（A: FAIL / B: FAIL）
- 生成时间：2026-10-23T13:29:32
- 验收器：independent: own geometry / C4 / structured-layer / metric recomputation; frozen v3c4.lift_cross.validate_payload_v4 (A: phase2_2d identity; B: generated row-swapped identity) for the authoritative 3D pass; frozen fslw strict pair audit for same-height crossings

## 逐组检查结果

| 组 | 结论 | core | artifacts | 检查数 | 失败项 |
|---|---|---|---|---:|---|
| A | FAIL | False | False | 23 | artefacts_ready_gate, authoritative_3d_validator, u_layer_assignment_artifact, opposite_assignment_artifact, figures, comparison_table_artifact |
| B | FAIL | False | False | 2 | ready_artifact, payload_file |

## 关键数字（独立重算）

| 指标 | V2 前基线 | 旧 Spatial U | A | B |
|---|---:|---:|---:|---:|
| routed | 1024 | 1024 | 1024 | — |
| unique_crossing_pairs | 23356 | 12824 | 19016 | — |
| same_layer_u_u_crossing_pairs | 104 | 0 | 0 | — |
| transitions | 440 | 824 | 952 | — |
| total_length_mm | 97495.8 | 98539 | 98034.5 | — |
| min_3d_clearance_mm | — | — | 2.3339e-05 | — |
| min_curvature_radius_mm | — | — | 15 | — |
| opposite_l2_routes | — | — | 220 | — |
| opposite_exception_routes | — | — | 52 | — |
| u_groups_reached | — | — | 64 | — |

## 逐高度交叉（独立重算，交叉对 / 波导数）

- **v2_pre_u_baseline**：0.0: 15952, 0.5: 7328, 1.0: 36, 1.5: 32, 2.0: 0, 2.5: 8
- **old_spatial_u_bundle**：0.0: 12160, 0.5: 116, 1.0: 528, 1.5: 16, 2.0: 0, 2.5: 4
- **A**：0.0: 18100, 0.5: 1008, 1.0: 932, 1.5: 0, 2.0: 0, 2.5: 0

## 各层波导数（独立重算）

- **v2_pre_u_baseline**：L1-z1=512, L1-z2=512, L2=124, L3=36, L4=24, L5=36
- **old_spatial_u_bundle**：L1-z1=512, L1-z2=512, L2=252, L3=80, L4=68, L5=12
- **A**：L1-z1=512, L1-z2=512, L2=220, L3=128, L4=64, L5=64

## 与生产 summary 的差异

### A（0 处差异）
- 无（独立重算与生产 summary 零差异）

### B（0 处差异）
- 无（独立重算与生产 summary 零差异）

> 说明：A/B 的 summary 关键指标均与独立重算一致。

## 权威 3D 验收（冻结 l3d validator）

- **A**：status=exploratory_only, exploratory_pass=False, formal_acceptance=False, counts={'violations': 190, 'contract_errors': 0, 'port_errors': 0, 'geometry_errors': 0, 'curvature_violations': 0, 'clearance_violations': 140, 'same_plane_violations': 50, 'self_clearance_violations': 0, 'other_errors': 0}, min_curvature=14.999999964, min_3d_clearance=2.3339e-05
- **B**：status=None, exploratory_pass=None, formal_acceptance=None, counts={}, min_curvature=None, min_3d_clearance=None

## A/B 组间一致性（B = A 的行/plane/端点交换）

- (A/B 未同时验收，无法做组间一致性检查)

## 生产对照表（comparison_table.json）检查

- 文件不存在（顶层对照表尚未生成）

## 产物与问题

- A artefacts_ready_gate: ARTEFACTS_READY missing (group not finalised)
- A u_layer_assignment_artifact: u_layer_assignment.json missing
- A opposite_assignment_artifact: opposite_assignment.json missing
- A figures: figures/ missing
- A comparison_table_artifact: comparison_table.json not generated yet
- B ready_artifact: READY not found (timeout after 5400.0s or --no-wait)
- B payload_file: routes_1024.json missing

> 说明：层高为探索性仿真参数（unconfirmed_simulation），几何 PASS 不等于制造工艺正式验收；本报告为独立重算。
