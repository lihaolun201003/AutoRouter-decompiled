# 结构化分层布线 A/B 独立几何验收报告

- 结论：**FAIL**（B: FAIL）
- 生成时间：2026-10-23T13:05:52
- 验收器：independent: own geometry / C4 / structured-layer / metric recomputation; frozen v3c4.lift_cross.validate_payload_v4 (A: phase2_2d identity; B: generated row-swapped identity) for the authoritative 3D pass; frozen fslw strict pair audit for same-height crossings

## 逐组检查结果

| 组 | 结论 | core | artifacts | 检查数 | 失败项 |
|---|---|---|---|---:|---|
| A | MISSING | - | - | 0 | - |
| B | FAIL | True | False | 1 | ready_artifact |

## 关键数字（独立重算）

| 指标 | V2 前基线 | 旧 Spatial U | A | B |
|---|---:|---:|---:|---:|
| routed | 1024 | 1024 | — | — |
| unique_crossing_pairs | 23356 | 12824 | — | — |
| same_layer_u_u_crossing_pairs | 104 | 0 | — | — |
| transitions | 440 | 824 | — | — |
| total_length_mm | 97495.8 | 98539 | — | — |
| min_3d_clearance_mm | — | — | — | — |
| min_curvature_radius_mm | — | — | — | — |
| opposite_l2_routes | — | — | — | — |
| opposite_exception_routes | — | — | — | — |
| u_groups_reached | — | — | — | — |

## 逐高度交叉（独立重算，交叉对 / 波导数）

- **v2_pre_u_baseline**：0.0: 15952, 0.5: 7328, 1.0: 36, 1.5: 32, 2.0: 0, 2.5: 8
- **old_spatial_u_bundle**：0.0: 12160, 0.5: 116, 1.0: 528, 1.5: 16, 2.0: 0, 2.5: 4

## 各层波导数（独立重算）

- **v2_pre_u_baseline**：L1-z1=512, L1-z2=512, L2=124, L3=36, L4=24, L5=36
- **old_spatial_u_bundle**：L1-z1=512, L1-z2=512, L2=252, L3=80, L4=68, L5=12

## 与生产 summary 的差异

### A（0 处差异）
- 无（独立重算与生产 summary 零差异）

### B（0 处差异）
- 无（独立重算与生产 summary 零差异）

> 说明：A/B 的 summary 关键指标均与独立重算一致。

## 权威 3D 验收（冻结 l3d validator）

- **A**：status=None, exploratory_pass=None, formal_acceptance=None, counts={}, min_curvature=None, min_3d_clearance=None
- **B**：status=None, exploratory_pass=None, formal_acceptance=None, counts={}, min_curvature=None, min_3d_clearance=None

## 产物与问题

- B ready_artifact: timeout after 5400.0s

> 说明：层高为探索性仿真参数（unconfirmed_simulation），几何 PASS 不等于制造工艺正式验收；本报告为独立重算。
