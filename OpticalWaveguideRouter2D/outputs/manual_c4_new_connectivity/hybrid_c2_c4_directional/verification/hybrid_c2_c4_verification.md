# Hybrid C2/C4 Directional Layer Routing — 独立验收报告

- 生成时间：2026-10-23T15:47:12
- 验证脚本：`C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\outputs\manual_c4_new_connectivity\hybrid_c2_c4_directional\verification\verify_hybrid_c2_c4.py` (sha256 `a621ef3916a06099…`)
- 独立性：未 import `four_side_1024.manual_c4.hybrid_c2_c4` / `run_hybrid_*`（运行时断言通过）；仅使用冻结 3D 校验入口 `validate_payload_v4`。

## 1. 验收结论

| 组 | 结论 | 关键检查 |
|---|---|---|
| H | **PASS** | 11/11 项检查通过 |
| V | **PASS** | 11/11 项检查通过 |

**总体结论：PASS** (H=PASS, V=PASS)

## 2. 核心数字（独立重算）

| 指标 | Hybrid H | Hybrid V | Structured A | Spatial U-bundle |
|---|---:|---:|---:|---:|
| 总布通数 | 1024 | 1024 | 1024 | 1024 |
| C2 二元组数 | 132 | 132 | — | — |
| C2 提升组数 | 64 | 64 | — | — |
| C2 失败组数 | 2 | 2 | — | — |
| z1 横纵同层交叉对 | 7032 | 7032 | 10928 | — |
| z=0 交叉对 | 11952 | 11952 | 17576 | — |
| L2 交叉对 | 0 | 0 | 1000 | — |
| 全局唯一交叉对 | 12960 | 12960 | 19584 | 12824 |
| 升降次数 | 784 | 784 | 944 | 824 |
| 三维总长 (mm) | 98019.9262 | 98019.9262 | 98033.7663 | 98539.0127 |
| 最小三维净空 (mm) | 0.0917 | 0.0917 | 0.0917 | 0.083207 |
| 最小曲率半径 (mm) | 15 | 15 | 15 | 15 |
| 独立 3D 验收 | exploratory_only | exploratory_only | exploratory_only | exploratory_only |
| C4 组数 | 144 | 144 | — | — |

层波导数（独立重算）：

| 层 | Hybrid H | Hybrid V | Structured A | Spatial |
|---|---:|---:|---:|---:|
| L1-z1 | 512 | 512 | 512 | 512 |
| L1-z2 | 512 | 512 | 512 | 512 |
| L2 | 136 | 136 | 216 | 252 |
| L3 | 128 | 128 | 128 | 80 |
| L4 | 64 | 64 | 64 | 68 |
| L5 | 64 | 64 | 64 | 12 |

削减量（独立计数口径）：z1 横纵同层交叉对 10928 → 7032（-3896）；z=0 交叉对 17576 → 11952（-5624）；全局唯一交叉对 19584 → 12960（-6624）。

> 口径说明：A 产物 summary 的逐高度交叉数字是交叉点数（z=0: 18600），crossing_analysis baseline 用逐高度唯一 route 对数（z=0: 17576）；全局唯一交叉对 19584 两口径一致。

## 3. 混合对称性（C2 180°+路径反转 / C4 90°）

> 方法：C2 二元组的物理固定端口关系是 `B_path(s) = R180(A_path(L - s))`（180° 旋转 **+ 遍历方向反转**：rise↔fall 对应、parts 顺序反转、direction 按旋转后的反向特征取负）；C4 组为纯 90° 旋转。两种关系都按弧长参数化对 3D 路径（XY 2D 链 + 升降 S 曲线）逐点比对（容差 1e-6），并额外核对 start/end、z0/z1、theta/footprint/length、from/to layer 等升降参数合同。

- **H**：z1 对边 132 个 C2 二元组（66 EW + 66 NS）全部满足 1e-6 容差 180° 严格旋转，最大偏差 7.11e-14 mm；z2 全部 144 个 C4 组（U 64 + 对边 2 + 邻边 78）的 432 个成员旋转比对全部通过，最大偏差 6.67e-14 mm；z1 邻边 46 组 （46 组）保持 Structured-A 的 C4 关系（最大偏差 4.02e-14 mm），不要求 C2 重排（其 3D 路径与 A 逐字段一致）。
- **V**：z1 对边 132 个 C2 二元组（66 EW + 66 NS）全部满足 1e-6 容差 180° 严格旋转，最大偏差 7.11e-14 mm；z2 全部 144 个 C4 组（U 64 + 对边 2 + 邻边 78）的 432 个成员旋转比对全部通过，最大偏差 6.67e-14 mm；z1 邻边 46 组 （46 组）保持 Structured-A 的 C4 关系（最大偏差 4.02e-14 mm），不要求 C2 重排（其 3D 路径与 A 逐字段一致）。

## 4. 固定保持（Structured A）

- **H**：U 256/256、z2 对边 8/8、邻边 496/496 与 Structured-A 记录逐字段一致（合同字段 0 差异；U 层序 / 端点 / parts 均一致）；含校验器内部注解 `_back_to_back_transitions` 在内的全部字段一致。
- **V**：U 256/256、z2 对边 8/8、邻边 496/496 与 Structured-A 记录逐字段一致（合同字段 0 差异；U 层序 / 端点 / parts 均一致）；含校验器内部注解 `_back_to_back_transitions` 在内的全部字段一致。

## 5. 分层规则与失败组

- **H**：提升方向 EW，64 组提升到 L2（层序 [1,2,1]，L2 平段 z=1.0，且 c2_pair_assignment 的 a_in/a_out、rise/fall 位置与实际几何一致）；保留方向 NS 66 组平铺 L1-z1；失败组 [2, 3] 在 c2_pair_assignment 中 failure 原因非空，实际保持 L1-z1 平铺。
- **V**：提升方向 NS，64 组提升到 L2（层序 [1,2,1]，L2 平段 z=1.0，且 c2_pair_assignment 的 a_in/a_out、rise/fall 位置与实际几何一致）；保留方向 EW 66 组平铺 L1-z1；失败组 [2, 3] 在 c2_pair_assignment 中 failure 原因非空，实际保持 L1-z1 平铺。

## 6. 几何与权威 3D 验收

> 设计约束：板面 150×150 mm、R=15 mm、波导宽 0.05 mm、最小中心线净空 0.08 mm、每条路线 0 或 2 次升降且只能落在 2D 直线段、完整 XYZ 碰撞检查由冻结 `validate_payload_v4` 执行。

- **H**：全部圆弧 R=15、直线轴对齐、升降均落在 2D 直线段、每条 0 或 2 个升降且先升后降、所有几何在 150×150 板内、非目标连接（632 条平铺 + 136 条重建）2D 链与 phase2_2d 一致。冻结 `validate_payload_v4` 复验：status=exploratory_only, exploratory_pass=True, formal_acceptance=False, 9 类 counts 全 0；min curvature=14.999999964 mm，min 3D clearance=0.091700023 mm (≥0.08)。
- **V**：全部圆弧 R=15、直线轴对齐、升降均落在 2D 直线段、每条 0 或 2 个升降且先升后降、所有几何在 150×150 板内、非目标连接（632 条平铺 + 136 条重建）2D 链与 phase2_2d 一致。冻结 `validate_payload_v4` 复验：status=exploratory_only, exploratory_pass=True, formal_acceptance=False, 9 类 counts 全 0；min curvature=14.999999964 mm，min 3D clearance=0.091700023 mm (≥0.08)。

## 7. 指标独立重算与生产 summary 对照

- **H**：summary / crossing_analysis 的交叉对数、z1 横纵、升降次数、三维总长、层波导数与独立重算 0 处差异、crossing_analysis 0 处差异、validation 报告 0 处差异。
- **V**：summary / crossing_analysis 的交叉对数、z1 横纵、升降次数、三维总长、层波导数与独立重算 0 处差异、crossing_analysis 0 处差异、validation 报告 0 处差异。

## 8. 失败与瓶颈（shadow bottleneck）

- **H**：`shadow_bottleneck_analysis.json` 结构自检通过（n_deep=34 = n_parallel 32 + no_feasible 2、n_crossing=0，深窗口集合与 feasibility 扫描一致）。32 个 deep_only 对列出的 blocker 均为 z2 接口层固定路线，且独立几何验证确认其单独就能封死整个最早窗口（a≤20 mm）；其中 21 个的深窗口阈值可由该 blocker 精确解释，11 个由额外 z2 接口层 shadow 进一步收紧（所有 binding obstacle 均为 z2 层 z=0.5 的固定几何）。2 个失败组（[2, 3]）经 2D/3D 几何枚举确认，升降足印 7.681146 mm：group 2: 2 条成员线、共 160 个对称候选 a 全部被固定 z2 几何阻挡（接口层 shadow 段 4 段 / L2 同线固定段 2 段）；group 3: 2 条成员线、共 160 个对称候选 a 全部被固定 z2 几何阻挡（接口层 shadow 段 4 段 / L2 同线固定段 2 段），故 feasibility 扫描为空表。
- **V**：`shadow_bottleneck_analysis.json` 结构自检通过（n_deep=34 = n_parallel 32 + no_feasible 2、n_crossing=0，深窗口集合与 feasibility 扫描一致）。32 个 deep_only 对列出的 blocker 均为 z2 接口层固定路线，且独立几何验证确认其单独就能封死整个最早窗口（a≤20 mm）；其中 21 个的深窗口阈值可由该 blocker 精确解释，11 个由额外 z2 接口层 shadow 进一步收紧（所有 binding obstacle 均为 z2 层 z=0.5 的固定几何）。2 个失败组（[2, 3]）经 2D/3D 几何枚举确认，升降足印 7.681146 mm：group 2: 2 条成员线、共 160 个对称候选 a 全部被固定 z2 几何阻挡（接口层 shadow 段 4 段 / L2 同线固定段 2 段）；group 3: 2 条成员线、共 160 个对称候选 a 全部被固定 z2 几何阻挡（接口层 shadow 段 4 段 / L2 同线固定段 2 段），故 feasibility 扫描为空表。

## 9. 产物完整性

- **H**：routes/c2_pair_assignment/validation/summary/crossing_analysis/READY/ARTEFACTS_READY 齐全；figures 13 PNG + 13 SVG 全部存在且格式有效。
- **V**：routes/c2_pair_assignment/validation/summary/crossing_analysis/READY/ARTEFACTS_READY 齐全；figures 13 PNG + 13 SVG 全部存在且格式有效。

## 10. 差异、口径与限制

- 独立性：脚本未 import 生产 hybrid 模块 (`four_side_1024.manual_c4.hybrid_c2_c4` / `run_hybrid_*`)；身份/对称/规则/几何/交叉指标全部独立实现，仅 3D 权威验收使用任务指定的冻结入口 `validate_payload_v4`。
- A 基线口径：A 产物 summary 的逐高度数字是**交叉点**数（z=0 为 18600）；本实验 crossing_analysis 的 baseline 使用**逐高度唯一 route 对**（z=0 为 17576）。两者全局唯一交叉对一致（19584）。H/V 结果两种口径分别为：z=0 唯一对 11952 / 交叉点 12464。
- 固定保持：H/V 两组的 760 条固定记录（U 256、z2 对边 8、邻边 496）与 Structured-A 记录逐字段完全一致（包括 l3d 校验器在 A 阶段写入的内部注解 `_back_to_back_transitions`，值 0）；仅本轮重新生成的 264 条 z1 对边记录（128 提升 + 136 平铺）不携带该内部注解，属预期且不影响几何/合同（冻结校验器会重新计算该注解）。
- 2D 链口径：`primitives` 参照字段在 896 条记录上与 phase2_2d 完全一致（128 条 C2 提升记录无该字段）；632 条接口平铺记录的实际 2D 链与 phase2_2d 一致；128 条 C2 提升 + 8 条 z2 对边提升记录由直线片段重建后与 phase2_2d 一致。U 256 条在 Structured A 中已按 U 线束重建（其实际 2D 链不等于 phase2_2d），本轮按任务要求保持与 A 逐字段一致（section 3 已验证）。
- 瓶颈结论：`shadow_bottleneck_analysis.json` 的 34 个深窗口对结论成立，但需精确表述：32 个 deep_only 对列出的 blocker 均为 z2 接口层固定路线的 parallel shadow，独立几何验证确认其单独封死 a≤20 mm 的最早窗口；其中部分对的精确深阈值由额外 z2 接口层 shadow 收紧。2 个失败组由 z2 接口层 shadow + L2 层占用共同导致不可行。
- 权威 3D：exploratory_pass=true、9 类 counts 全 0、formal_acceptance=false（层高为未确认仿真参数，formal 被拒是预期行为）；min 3D clearance 0.0917 mm > 0.08 mm，min curvature 14.999999964 mm ≥ 15 mm - 容差。
- 限制：交叉指标采用“中心线交点/唯一 route 对”几何口径（与生产 strict policy 的 crossings 定义一致，独立实现已逐项复现生产数字）；未对图形内容做像素级复核，仅校验 13×2 图像文件存在、格式与尺寸；Spatial U-bundle 仅交叉计数做了独立交叉核对，其余指标引用其产物。

## 11. 输出文件

- `_group_H.json`
- `_group_V.json`
- `hybrid_c2_c4_verification.json`
- `hybrid_c2_c4_verification.md`
