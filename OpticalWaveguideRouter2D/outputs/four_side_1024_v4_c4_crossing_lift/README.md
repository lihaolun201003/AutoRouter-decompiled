# V4-C4 交叉规避式三维抬升实验 — 数据清单

> **发布口径说明（2026-10-21）**：下表原记录中的 56,032 实为逐高度的 flat-part 审计对象对数；抬升路线的首尾分段可能让同一线路对重复计数。最终按“高度 + 线路对”去重为 **55,616**，跨高度再去重为 **55,596**。因此原表的“同高度交叉线路对”标签及 -35.2% 不能直接当作唯一线路对口径。
>
> `summary.json` 的 `high_layer_crossing_pairs=908` 与 `added_high_crossing_pairs_total=456` 是回退前累计/历史增量字段；最终高层唯一线路对为 **444**，相对原始布局新增全局线路对为 **320**。`remaining_crossing_pairs` 仅保留前 50,000 项。原始路线和统计文件保持原件，全部口径与哈希见 [上传校验清单](../../../UPLOAD_MANIFEST_20261021_v4_c4_crossing_lift.json)；三维验收仍为探索性通过，`formal_acceptance=false`。

在 **V4 1020/1024**（严格 C4、验收 PASS）的基础上，**不改变任何 XY 路径、端口与连接关系**，
把同高度交叉密集的 C4 四元组整体抬升到 L2–L5，减少同高度交叉。核心规则：

- 升降过渡（R15 S 形曲线）**只能放在原 2D 路径的直线段上**；圆弧整段保持恒定 Z，圆弧内绝不升降；
- 交叉落在圆弧上时，在**进入圆弧前的直线段提前抬升**，用高层直线/圆弧跨越后再下降；
- 相近交叉**合并为一个抬升区间**（每条线路最多一个 climb + 一个 descent，不反复升降）；
- 以四元组为单位：只搜索代表线路，其余三条由 90°/180°/270° 旋转生成（Z 高度一致），
  四条联合真实 XYZ 检查，原子提交；
- 每轮重新计算交叉关系，只保留使同高度交叉对严格减少的方案。

## 最终结果

| 指标 | 优化前 | 优化后 |
|---|---:|---:|
| 布通通道数 | 1020 | **1020**（不变） |
| 同高度交叉线路对 | **86504** | **56032**（减少 **30472 对，-35.2%**） |
| 同高度交叉点 | 92196 | 57812 |
| 抬升四元组 | 0 | **86 / 255**（z1 77 组 + z2 9 组；L2 36 / L3 17 / L4 18 / L5 15） |
| 升降次数（climb+descent） | 0 | **688**（344 条抬升路线 × 2） |
| 三维路线总长度 | 131315.98 mm | **131433.95 mm（+117.97 mm，+0.09%）** |
| 验收 | PASS | **PASS**（`l3d.validate_l3d`：0 违规、0 端口错、0 净空错；C4 旋转 255/256 组完整、0 误差） |

分层剩余交叉对：L1 row1 z=0 45856、L1 row2 z=0.5 9732、L2 192、L3 118、L4 42、L5 92。
新增的高层合法交叉对 320 对（均为 L2–L5 上通过冻结 2D strict 与独立 3D 验证的 90° 合法交叉；
L1 原有交叉对全部不增加）；另有 12 个四元组在最终验收修复轮中回退（避免任何非法近距）。

层高为现有探索性配置：L2/L3/L4/L5 = 1.0/1.5/2.0/2.5 mm（provenance=unconfirmed），
因此三维验收为 **exploratory PASS**，formal acceptance 不允许（继承程序规定）。

## 文件

| 文件 | 说明 |
|---|---|
| `routes_l3d.json` | **完整三维路线 JSON**：1024 条记录（1020 routed + 4 failed），routed 记录含 `parts`（flat 层内线段/圆弧 + transition 升降段）、真实 XYZ/Z、层高、`length_mm`/`xy_length_mm`、`layer_sequence` |
| `lift_plans.json` | 每个 C4 四元组的实际抬升方案（层号、climb/fall 弧长位置、高跨区间、消除交叉点数/对数、长度增量）+ 被拒方案统计 |
| `crossings_before.json` / `crossings_after.json` | 优化前后全部同高度交叉点（含坐标、交叉线路对）与剩余交叉线路对 |
| `summary.json` | 全部指标：前后交叉数/点、分层分布、抬升四元组、升降次数、长度变化、新增高层合法交叉、参数、耗时、验证状态 |
| `checkpoint.json` | 最优结果 checkpoint（抬升四元组、路线列表、前后交叉数、回退组、耗时） |
| `layer_stack.json` | L2–L5 探索性层高配置 |
| `validation.json` | 独立 3D 验证器输出（PASS，exploratory） |
| `plots/` | 5 类实际布线图（PNG+SVG，均由 `routes_l3d.json` 真实路线生成） |
| `run.log` / `checkpoints/step_*.json` | 逐轮日志与中间 checkpoint（每提升一次保存） |

## 图（plots/）

1. `01_before_after_xy` 原始二维与优化后 XY 俯视对比（按实际 Z 着色）
2. `02_3d_full` 完整三维布线图（按实际 Z 高度区分颜色，含 S 形升降段）
3. `03_layers` L1–L5 分层布线图（L1 两排 + L2–L5 实际抬升线路）
4. `04_early_climb_zoom` 圆弧前提前抬升局部放大图（红粗线 = 保持高层恒定 Z 的 R15 圆弧）
5. `05_crossing_region_before_after` 交叉密集区域优化前后对比

## 复现

```powershell
$env:PYTHONPATH = "...\OpticalWaveguideRouter2D"
# 需要 matplotlib + scipy 的 .venv Python
& $py -m four_side_1024.v3c4.lift_cross_run --max-groups 150 --time-limit 3000
```

实现位置：`four_side_1024/v3c4/lift_cross.py`（抬升规划、交叉检测、四元组原子提交、真三维检查）
与 `four_side_1024/v3c4/lift_cross_run.py`（运行、验收修复轮、汇总与 5 类图输出）。
复用现有 `l3d/` 的 S 形过渡几何、层高模型、`l3d.world.World` 真三维碰撞与 `l3d.validate_l3d` 验证器；
未修改 V4 CSV / V4 1020 条路线数据 / V1-V2 历史结果。

主要参数：R=15 mm；板 150×150 mm；width 0.05；edge gap 0.03；clearance 0.08 mm；
过渡 port margin 1.2 mm、segment margin 0.25 mm、安全低 Z 段 1.8 mm、最小高跨直线 5 mm；
最多 60 个候选/四元组；总耗时约 698 s（32 核机器单进程）。
