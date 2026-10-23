# MANUAL-C4 新连接表 1024 通道 C4 二维/三维布线实验（数据清单）

本目录是用**全新人工连接表**重做的 1024 通道 C4 对称二维与三维光波导布线实验的
完整产物。所有算法复用仓库既有已验收实现（`four_side_1024/v2opt` + `d56` +
`fslw` + `r15` + `v3c4` + `l3d`），未引入自适应弯曲半径、多次升降或 Native 3D
联合寻路等新算法；未覆盖任何历史输出目录。

## 输入

| 文件 | 说明 |
|---|---|
| `inputs/manual_z1_c4_full.csv` | 人工 z1 平面连接表原始文件（512 条，副本） |
| `inputs/manual_z2_c4_full.csv` | 人工 z2 平面连接表原始文件（已转换 row2 编号，512 条，副本） |
| `inputs/connectivity_1024.csv` | 合成拓扑表（12 列，route_id 1..512 = z1 / 513..1024 = z2），与既有 V3/V4 拓扑 CSV 同 schema |
| `inputs/connectivity_1024.json` | 1024 条连接身份 + 256 个 C4 四元组 + 逐平面校验记录 |
| `inputs/input_validation.json` | 输入/兼容性验收（端口身份、1024 端口各用一次、C4 闭合、与既有代码数据结构兼容性） |
| `inputs/feasibility.json` | R=15 mm 下的几何可行性（同边间距 ≥ 2R、邻边腿长、对边横向偏移） |

连接构成（严格 C4 对称，每平面 128 组 × 4 条）：

- z1（row 1, z=0 mm）：512 条 = 对边 264 + 邻边 184 + 同边 64
- z2（row 2, z=0.5 mm）：512 条 = 邻边 312 + 同边 192 + 对边 8
- 合计 1024 条、2048 物理端口各用一次、C4 闭合 90/180/270 全 0 缺失

## 阶段 2：二维 C4 布线（`phase2_2d/`）

- 输入：`inputs/connectivity_1024.csv`；从零布线，不使用任何旧路线。
- 采用既有 C4 二维算法：代表连接搜索 + 90/180/270 精确旋转 + 四条联合检查 + 原子提交；
  候选族 = 冻结 `v2opt.candext`（D56 直线/90° R15 弧/short-S）+ 既有 R15 同边 U 族
  （quarter-pair，R=15 不缩）。
- 逐平面结果：`z1/routes.json`、`z2/routes.json`（含全部 20 列身份与 `primitives`）、
  `run_summary.json`、`validation.json`（fslw strict 审计 + C4 旋转审计）、
  `checkpoint.json`、`run.log`。
- 合并结果：`routes_1024.json`（1024 条完整 XY 路线 + 256 组状态 + 交叉统计）、
  `routes_z1.json` / `routes_z2.json`、`failed_routes.json`（本轮为空）、
  `validation.json`（独立验收汇总）。
- 图：`plots/01_overview_1024`（两平面总览）、`02_row1_z1`、`03_row2_z2`、
  `04_same_side_u_zoom`（同边 U 局部放大），PNG + SVG。

## 阶段 3：初始三维交叉抬升（`phase3_initial_lift/`）

- 输入：`phase2_2d/routes_1024.json`（同一批 XY 路线，固定不重算）。
- 算法：既有 V4-C4 交叉规避式抬升（`v3c4/lift_cross.py`），C4 四元组联合抬升，
  只在原二维直线段升降，每个四元组原子提交，层栈 L2–L5 = 1.00/1.50/2.00/2.50 mm。
- 产物：`routes_l3d.json`（完整 XYZ 路线）、`lift_plans.json`（逐四元组抬升方案）、
  `layer_stack.json`、`crossings_before.json` / `crossings_after.json`（含剩余唯一
  (route_id_a, route_id_b) 对）、`summary.json`、`validation.json`（独立 l3d 几何验收，
  探索性层高 → exploratory PASS）、`checkpoints/`、`run.log`、`plots/`（整体 3D / 分层 /
  局部放大）。

## 阶段 4：A/B/C/D 层高对照（`phase4_ablation/`）

四组固定层高（L2/L3/L4/L5，mm），同一批 XY 路线、同一算法与预算、互不共享已抬升结果：

| 组 | L2/L3/L4/L5 (mm) | 目录 |
|---|---|---|
| A | 0.75 / 1.00 / 1.25 / 1.50 | `phase4_ablation/A_0.25mm/` |
| B | 1.00 / 1.50 / 2.00 / 2.50 | `phase4_ablation/B_0.50mm/` |
| C | 1.25 / 2.00 / 2.75 / 3.50 | `phase4_ablation/C_0.75mm/` |
| D | 1.50 / 2.50 / 3.50 / 4.50 | `phase4_ablation/D_1.00mm/` |

每组目录与阶段 3 同结构；另有 `baseline_crossings.json`（共享未抬升基线交叉缓存）、
`ablation_table.json` / `ablation_table.md`（对照表）与
`ablation_3d_compare.png/svg`（四组统一视角 3D 对照图）。

## 阶段 5：三维动态优化 V2（`phase5_dynamic_optimization/`）

以阶段 4 的 **B 组**（0.50 mm）为输入，执行单一四元组换层/区间调整、双四元组联合
重调度、失败四元组重试；每次动作要求全局唯一交叉线路对严格减少，提交前做独立 XYZ
几何验收。

- `before/`：B 组输入快照（routes_l3d/lift_plans/layer_stack/validation/summary）
- `after/`：优化后完整 XYZ 路线（`routes_l3d.json`）、层分配
  （`layer_assignments.json`）、`validation.json`
- `actions.json`：接受/拒绝动作记录；`stage_records.json`：换层/区间移动/联合调度/
  失败重试分阶段记录；`summary.json`、`checkpoint.json`、`figures/`（优化前后 3D 与
  联合调度局部放大）、`run.log`、`input_hashes.json`

## 附加可视化：z2（row2）逐层独立三维图（`z2_layer_visualization/`）

基于阶段 5 最终结果 `phase5_dynamic_optimization/after/routes_l3d.json` 的**纯可视化**
（不重新布线、不修改任何路线/层高/连接）：只渲染原始 z2 的 512 条波导（z1/row1 完全隐藏），
每张图只包含**在该层有 flat（水平传播）段**的波导，并绘制其完整 XYZ 路线（含升降段与其他
高度部分；仅在升降 S 曲线中经过该高度的波导不计入）。

| 文件 | 层 / 物理高度 | 波导数 |
|---|---|---:|
| `L1_z2_3d.png/.svg` | L1-z2，z = 0.5 mm（接口层 row2） | 512 |
| `L2_3d.png/.svg` | L2，z = 1.0 mm | 8 |
| `L3_3d.png/.svg` | L3，z = 1.5 mm | 16 |
| `L4_3d.png/.svg` | L4，z = 2.0 mm | 20 |
| `L5_3d.png/.svg` | L5，z = 2.5 mm | 28 |

五图使用完全相同的坐标范围（x/y −5..155 mm、z −0.1..2.7 mm）、视角（elev 26°, azim
−58°）、比例与画布（3036×2576 px，230 dpi）；`layer_counts.json` 记录各层数量、
route_id 列表、判定口径与源文件 sha256。生成脚本：
`four_side_1024/manual_c4/z2_layer_plots.py`。

### z1（row1）逐层独立三维图（`z1_layer_visualization/`，同样式）

与 z2 完全同口径、同坐标/视角/画布，仅渲染原始 **z1 的 512 条**（z2/row2 完全隐藏）：

| 文件 | 层 / 物理高度 | 波导数 |
|---|---|---:|
| `L1_z1_3d.png/.svg` | L1-z1，z = 0.0 mm（接口层 row1） | 512 |
| `L2_3d.png/.svg` | L2，z = 1.0 mm | 116 |
| `L3_3d.png/.svg` | L3，z = 1.5 mm | 20 |
| `L4_3d.png/.svg` | L4，z = 2.0 mm | 4 |
| `L5_3d.png/.svg` | L5，z = 2.5 mm | 8 |

z1 中 148 条被抬升（L2–L5 分别为 116/20/4/8，合计 148），因此跨层 appearances
= 512 + 148 = 660。`z1_layer_visualization/layer_counts.json` 含各层 route_id 列表。

## 空间分组式 U 形线束三维布线优化（`spatial_u_bundle_optimization/`）

基于阶段 5（动态优化 V2）的 1024/1024 结果，对指定的 64 个同边 U 形 C4 四元组
（group 20–35 → L2、144–159 → L2、160–175 → L3、176–191 → L4，共 256 条）重构造
"延长入口直线 → S 上升 → 目标层 90°圆弧 + 中间直线 + 90°圆弧 → S 下降 → 延长出口
直线"的空间分组式三维线束，其余路线保持。结果：目标分层 **64/64**、1024/1024 布通、
全局唯一交叉对 **23,356 → 12,824**（仅修改 U 的 u-only 变体为 12,408）、同层 U-U
交叉对 **104 → 0**；两版均独立 3D 几何验收 exploratory PASS。阻挡的非 U 四元组
（group 11）在 final 变体中被重抬到 L5 并逐条记录，u-only/final 分开对照。详见该目录
`README.md`、`comparison_table.md` 与 `verification/`。

## 验收与报告

- `verification/`：**独立验收脚本与报告**（不 import 生产代码，从原始 CSV + 权威端口
  模型独立重算），覆盖输入、阶段 2、阶段 3/4/5 的几何与统计口径。
- `SUMMARY.md`：交付索引 + 汇总结果；`comparison_table.md/json`：与旧 V4-C4 的对照表。
- `CODE_CHANGES.md`：本轮对既有代码的必要参数化记录（默认行为不变）。

## 复现命令（PowerShell，仓库根目录）

```powershell
$py = ".venv\Scripts\python.exe"
$env:PYTHONPATH = (Get-Location).Path

# 阶段 1：输入校验 + 合成拓扑
& $py -m four_side_1024.manual_c4.connectivity

# 阶段 2：逐平面二维布线（可并行）+ 合并验收
& $py -m four_side_1024.manual_c4.run2d plane --plane z1 --order easy --budget 1600 --rr-rounds 2 --retry-passes 3 --out outputs/manual_c4_new_connectivity/phase2_2d/z1
& $py -m four_side_1024.manual_c4.run2d plane --plane z2 --order easy --budget 1600 --rr-rounds 2 --retry-passes 3 --out outputs/manual_c4_new_connectivity/phase2_2d/z2
& $py -m four_side_1024.manual_c4.run2d combine --phase2-dir outputs/manual_c4_new_connectivity/phase2_2d
& $py -m four_side_1024.manual_c4.plots2d --phase2-dir outputs/manual_c4_new_connectivity/phase2_2d

# 阶段 3：初始三维交叉抬升
& $py -m four_side_1024.v3c4.lift_cross_run --out outputs/manual_c4_new_connectivity/phase3_initial_lift --v4-root outputs/manual_c4_new_connectivity/phase2_2d --max-groups 150 --time-limit 3000

# 阶段 4：A/B/C/D 层高对照
& $py -m four_side_1024.v3c4.ablation --root outputs/manual_c4_new_connectivity/phase4_ablation --v4-root outputs/manual_c4_new_connectivity/phase2_2d --label MANUAL-C4 --full --max-groups 150 --time-limit 3000

# 阶段 5：B 组动态优化 V2
& $py -m four_side_1024.v3c4.dynamic_run --out outputs/manual_c4_new_connectivity/phase5_dynamic_optimization --b-root outputs/manual_c4_new_connectivity/phase4_ablation/B_0.50mm --cache outputs/manual_c4_new_connectivity/phase4_ablation/baseline_crossings.json --v4-root outputs/manual_c4_new_connectivity/phase2_2d --label MANUAL-C4 --time-limit 3600

# 对照表与摘要
& $py -m four_side_1024.manual_c4.report

# 附加：逐层独立三维图（--plane z2 为 row2；--plane z1 为 row1）
& $py -m four_side_1024.manual_c4.z2_layer_plots --plane z2
& $py -m four_side_1024.manual_c4.z2_layer_plots --plane z1
```

## 物理约束（全部沿用，未放宽）

板 150×150 mm；R=15 mm（所有圆弧，含同边 U 与升降 S 曲线）；波导宽 0.05 mm；
非豁免最小中心线净空 0.08 mm；row1 z=0 mm / row2 z=0.5 mm；端口位置与出入射方向固定；
严格 C4 四重旋转（每四元组四条路线互为 90° 旋转）；升降只在原二维直线段、圆弧内部
禁止升降、每条波导最多一次上升与一次下降；交叉统计跨全部物理高度按唯一
(route_id_a, route_id_b) 去重。L2–L5 层高为**探索性工艺假设**，几何 PASS 不等于
制造工艺正式验收。
