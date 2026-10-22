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
```

## 物理约束（全部沿用，未放宽）

板 150×150 mm；R=15 mm（所有圆弧，含同边 U 与升降 S 曲线）；波导宽 0.05 mm；
非豁免最小中心线净空 0.08 mm；row1 z=0 mm / row2 z=0.5 mm；端口位置与出入射方向固定；
严格 C4 四重旋转（每四元组四条路线互为 90° 旋转）；升降只在原二维直线段、圆弧内部
禁止升降、每条波导最多一次上升与一次下降；交叉统计跨全部物理高度按唯一
(route_id_a, route_id_b) 去重。L2–L5 层高为**探索性工艺假设**，几何 PASS 不等于
制造工艺正式验收。
