# 结构化分层布线 A/B 独立几何验收报告

- 结论：**FAIL**（A: PASS / B: FAIL）
- 生成时间：2026-10-23T14:42:33
- 验收器：independent: own geometry / C4 / structured-layer / metric recomputation; frozen v3c4.lift_cross.validate_payload_v4 (A: phase2_2d identity; B: generated row-swapped identity) for the authoritative 3D pass; frozen fslw strict pair audit for same-height crossings

## 逐组检查结果

| 组 | 结论 | core | artifacts | 检查数 | 失败项 |
|---|---|---|---|---:|---|
| A | PASS | True | True | 26 | — |
| B | FAIL | False | True | 27 | legacy_z_mm_field, rule_u_target_layers, u_quartet_geometry |

## A 组结论（最优：完全达标）

- verdict=PASS，core=True，artifacts=True；检查 26 项全部通过。
- 权威 3D：status=exploratory_only，exploratory_pass=True，9 类 counts={'violations': 0, 'contract_errors': 0, 'port_errors': 0, 'geometry_errors': 0, 'curvature_violations': 0, 'clearance_violations': 0, 'same_plane_violations': 0, 'self_clearance_violations': 0, 'other_errors': 0}；min curvature=14.999999964 mm，min 3D clearance=0.091700023 mm。
- 规则分层：邻边 496 条接口层；对边 216 条 L2（54/68 组），例外 56 条（原因逐组记录）；U 64/64 组全部到达目标层。
- 指标：唯一交叉对 19584，升降 944，总长 98033.7663 mm，同层 U-U 交叉对 0。
- 结论：A 组是唯一完整满足**规则分层 + 严格 C4 + 冻结 3D 验收**全部要求的组，可作为结构化分层布线的参考方案；其代价是对边集中 L2 后NS×EW 直通线在 z=1.0 产生 1000 对 90° 交叉，唯一交叉对因此高于旧 Spatial-U 基线。

## B 组结论与失败瓶颈

- verdict=**FAIL**；分离结论：**几何/权威 3D PASS + 边界约束 PASS**，**U 规则分层未达标（16/64 组）**。
- 权威 3D（B 用行交换 identity root）：status=exploratory_only，exploratory_pass=True，9 类 counts={'violations': 0, 'contract_errors': 0, 'port_errors': 0, 'geometry_errors': 0, 'curvature_violations': 0, 'clearance_violations': 0, 'same_plane_violations': 0, 'self_clearance_violations': 0, 'other_errors': 0}；min curvature=14.999999965 mm，min 3D clearance=0.084933506 mm。
- 对边规则：66/68 组 L2（264 条），例外 2 组（208、209，原因：{"208": "该对边四元组在 B 的全平铺基世界下无可行 (a,D)，保留接口层平铺（几何合法）", "209": "该对边四元组在 B 的全平铺基世界下无可行 (a,D)，保留接口层平铺（几何合法）"}）；邻边 496 条接口层；C4 严格旋转检查全部通过。
- U 分层：达标 16/64 组；失败 48 组，按 bundle 分布：
  - z1_middle (gid 20–35, →L3): 6 组失败 → [20, 21, 22, 23, 24, 25]
  - z2 corner U #1 (gid 144–159, →L3): 16 组失败 → [144, 145, 146, 147, 148, 149] …
  - z2 corner U #2 (gid 160–175, →L4): 16 组失败 → [160, 161, 162, 163, 164, 165] …
  - z2 middle U (gid 176–191, →L5): 10 组失败 → [182, 183, 184, 185, 186, 187] …
- 失败原因分布（来自 summary.u_failures / u_layer_assignment，逐组非空）：
  - 48 组：行交换后本 U 四元组落到 z=0 基排，其端口列（两排端口共享同一 XY）在z=0.5 行被对边连接占用；从 z=0 抬升的 S 过渡必须在同列穿越 z=0.5 平面，与对边连接的 base/过渡在 0.08mm 净空、C4 同时升降与单次升降约束下冲突，角部 32 组结构性不可行；其余为全平铺基…
- 失败证据：B 的层计数 L3=40、L4=0、L5=24，仅 16 组 U 四元组有目标层平段；其余 48 组的 4 条路线保持接口平铺（u_layer_assignment.json 中 status=failed 且 failure 非空）。
  - gid 20（目标 L3） route_ids=[39, 131, 249, 250] reason=行交换后本 U 四元组落到 z=0 基排，其端口列（两排端口共享同一 XY）在z=0.5 行被对边连接占用；从 z=0 抬升的 S 过渡必须在同列穿越 z=0.5 平面，与对边连接的 base/过渡在 0.08mm 净空、C4 同时升降与单次升降约束下冲突，角部 32 组结构性不可行；其余为全平铺基世界过密无可行 (a,D)。保持接口层平铺（合法），作为规则…
  - gid 21（目标 L3） route_ids=[40, 132, 251, 252] reason=行交换后本 U 四元组落到 z=0 基排，其端口列（两排端口共享同一 XY）在z=0.5 行被对边连接占用；从 z=0 抬升的 S 过渡必须在同列穿越 z=0.5 平面，与对边连接的 base/过渡在 0.08mm 净空、C4 同时升降与单次升降约束下冲突，角部 32 组结构性不可行；其余为全平铺基世界过密无可行 (a,D)。保持接口层平铺（合法），作为规则…
  - gid 22（目标 L3） route_ids=[41, 133, 253, 254] reason=行交换后本 U 四元组落到 z=0 基排，其端口列（两排端口共享同一 XY）在z=0.5 行被对边连接占用；从 z=0 抬升的 S 过渡必须在同列穿越 z=0.5 平面，与对边连接的 base/过渡在 0.08mm 净空、C4 同时升降与单次升降约束下冲突，角部 32 组结构性不可行；其余为全平铺基世界过密无可行 (a,D)。保持接口层平铺（合法），作为规则…
- 根因（与生产定位一致，独立复核数据吻合）：行交换后原 z2 表的 U 四元组落到 z1 基排（z=0.0），而原 z1 表的对边连接落到 z2 基排（z=0.5）并从 0.5 抬升 L2；两排端口共享同一 XY，U 从 z=0 抬升的 S 过渡必须在同列穿越 z=0.5 平面，与对边连接的 base/过渡在 0.08 mm 净空、C4 同时升降与单次升降约束下无法同时满足 → corner1/corner2 共 32 组结构性不可行；另有 16 组 middle U 在全平铺基世界过密条件下无可行 (a,D)。
- 其它观察：B 因对边 L2 抬升窗口偏小，z=1.0 层直通段很长，L2 层交叉对达 12080 （A 为 1000）；B 的同层 U-U 交叉对为 1320 （A 为 0，旧 Spatial 为 0），是 B 交叉总数 26152 远高于 A 19584 的主因。

## 独立复算与生产 summary 的差异（应为零）

- **A**：0 处数值差异（独立重算与生产 summary 一致）
- **B**：0 处数值差异（独立重算与生产 summary 一致）

> 说明：B 的 summary 采用另一套字段命名（省略 opposite_on_L2_* / u_rebuilt_routes / experiment 标签，改为 opposite_l2_* / u_target_reached_groups 等），独立验收按等价字段/推导值核对后数值零差异；schema 差异以 warning 记录。

## 关键数字（独立重算）

| 指标 | V2 前基线 | 旧 Spatial U | A | B |
|---|---:|---:|---:|---:|
| routed | 1024 | 1024 | 1024 | 1024 |
| unique_crossing_pairs | 23356 | 12824 | 19584 | 26152 |
| same_layer_u_u_crossing_pairs | 104 | 0 | 0 | 1320 |
| transitions | 440 | 824 | 944 | 656 |
| total_length_mm | 97495.8 | 98539 | 98033.8 | 99554.3 |
| min_3d_clearance_mm | 0.0832073 | 0.0832073 | 0.0917 | 0.0849335 |
| min_curvature_radius_mm | 15 | 15 | 15 | 15 |
| opposite_l2_routes | — | — | 216 | 264 |
| opposite_exception_routes | — | — | 56 | 8 |
| u_groups_reached | — | — | 64 | 16 |

## 逐高度交叉（独立重算，交叉对 / 波导数）

> 交叉对数按生产/冻结 fslw 的 `crossing_pair_count` 口径（同一线路的 L1 两个平段与同一条线路相交时会被计两次）；逐高度“逻辑唯一 route 对”见 JSON 中的 `own_geometry_crossings`，其集合与冻结 fslw 审计完全一致，“波导数”等于唯一交点计数。

- **v2_pre_u_baseline**：0.0: 15952, 0.5: 7328, 1.0: 36, 1.5: 32, 2.0: 0, 2.5: 8
- **old_spatial_u_bundle**：0.0: 12160, 0.5: 116, 1.0: 528, 1.5: 16, 2.0: 0, 2.5: 4
- **A**：0.0: 18600, 0.5: 1008, 1.0: 1000, 1.5: 0, 2.0: 0, 2.5: 0
- **B**：0.0: 11624, 0.5: 2768, 1.0: 12080, 1.5: 0, 2.5: 0

## 各层波导数（独立重算）

- **v2_pre_u_baseline**：L1-z1=512, L1-z2=512, L2=124, L3=36, L4=24, L5=36
- **old_spatial_u_bundle**：L1-z1=512, L1-z2=512, L2=252, L3=80, L4=68, L5=12
- **A**：L1-z1=512, L1-z2=512, L2=216, L3=128, L4=64, L5=64
- **B**：L1-z1=512, L1-z2=512, L2=264, L3=40, L4=0, L5=24

## 与生产 summary 的差异

### A（0 处差异）
- 无（独立重算与生产 summary 零差异）

### B（0 处差异）
- 无（独立重算与生产 summary 零差异）

> 说明：A/B 的 summary 关键指标均与独立重算一致。

## 权威 3D 验收（冻结 l3d validator）

- **A**：status=exploratory_only, exploratory_pass=True, formal_acceptance=False, counts={'violations': 0, 'contract_errors': 0, 'port_errors': 0, 'geometry_errors': 0, 'curvature_violations': 0, 'clearance_violations': 0, 'same_plane_violations': 0, 'self_clearance_violations': 0, 'other_errors': 0}, min_curvature=14.999999964, min_3d_clearance=0.091700023
- **B**：status=exploratory_only, exploratory_pass=True, formal_acceptance=False, counts={'violations': 0, 'contract_errors': 0, 'port_errors': 0, 'geometry_errors': 0, 'curvature_violations': 0, 'clearance_violations': 0, 'same_plane_violations': 0, 'self_clearance_violations': 0, 'other_errors': 0}, min_curvature=14.999999965, min_3d_clearance=0.084933506

## A/B 组间一致性（B = A 的行/plane/端点交换）

- cross_group_consistency: PASS

## 生产对照表（comparison_table.json）检查

- 文件：C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\outputs\manual_c4_new_connectivity\structured_layer_routing\comparison_table.json (sha256=388ccb82fea547c10c24bab9dad539a698497ce08a8dafd85a8bdad000744998)
- 结果：PASS，匹配 8 项，不匹配 0 项

## 产物清单

| 组 | routes | summary | validation | u_assignment | opposite_assignment | ARTEFACTS_READY | READY | figures |
|---|---|---|---|---|---|---|---|---|
| A | yes | yes | yes | yes | yes | yes | yes | 30 files |
| B | yes | yes | yes | yes | yes | yes | yes | 30 files |

## 产物与问题

- B warning: record z_mm legacy field inconsistent with physical row on 1024 records (not used by the geometry or the frozen validator): [{'route_id': 1, 'z_mm': 0.0, 'plane': 'z2'}, {'route_id': 2, 'z_mm': 0.0, 'plane': 'z2'}, {'route_id': 3, 'z_mm': 0.0, 'plane': 'z2'}]
- B warning: production summary omits opposite_total_routes; the equivalent value is recomputed from the payload (272)
- B warning: production summary omits u_rebuilt_routes; the equivalent value is recomputed from the payload (64)
- B warning: producer summary has no experiment label (schema variant)

> 说明：层高为探索性仿真参数（unconfirmed_simulation），几何 PASS 不等于制造工艺正式验收；本报告为独立重算。
