# V4-C4 L2–L5 层间距敏感性对照实验（交叉规避式三维抬升）

> **发布校验说明（2026-10-22）**：本轮主指标是跨所有高度去重的唯一线路对，使用 `remaining_unique_crossing_pairs`：A/B/C/D 分别为 **47,192 / 55,484 / 46,112 / 45,204**。部分 `summary.json` 仍保留按 flat-part 审计对象计数的 `crossing_pairs_after` 及历史高层累计字段，不能与唯一线路对混用。几何验收仅为探索性通过，正式制造验收仍未成立。详见 [本次上传校验清单](../../../UPLOAD_MANIFEST_20261022_layer_studies.json)。

唯一变量：L2–L5 的物理层高。四组实验都从**同一个 V4 未抬升基线**（1020/1024 已布通、
2048 端口、严格 C4）独立开始，使用完全相同的交叉检测、候选排序、评分权重与搜索策略，
相同预算（`max_groups=150`，`time_limit=3000 s`）。固定条件：两排接口 z=0 / 0.5 mm、
R=15 mm、波导宽 0.05 mm、非豁免 3D 中心线净空 0.08 mm、边缘间距 0.03 mm；
升降只允许在原 2D 路径直线段上，圆弧整段保持恒定 Z，四元组旋转+联合 3D 检查+原子提交。

## 四组对照表

| 指标 | 0.25 mm (A) | 0.50 mm (B，原配置) | 0.75 mm (C) | 1.00 mm (D) |
|---|---:|---:|---:|---:|
| 层高 L2/L3/L4/L5 (mm) | 0.75/1.00/1.25/1.50 | 1.00/1.50/2.00/2.50 | 1.25/2.00/2.75/3.50 | 1.50/2.50/3.50/4.50 |
| 布通数 | 1020 | 1020 | 1020 | 1020 |
| 剩余唯一交叉线路对 | **47192** | **55484** | 46112 | **45204** |
| 交叉减少比例 | 45.45% | 35.86% | 46.69% | **47.74%** |
| 抬升四元组数量 | 88 | 83 | **102** | 97 |
| 实际升降次数 | 704 | 664 | 816 | 776 |
| 总三维路线长度增量 | +66.642 mm | +111.308 mm | +261.668 mm | +369.942 mm |
| 最小三维净空 | 0.0815 mm | 0.0895 mm | 0.0812 mm | 0.0831 mm |
| 运行时间 | 813.5 s | 837.7 s | 776.4 s | 969.2 s |
| 预算终止原因 | no_more_candidates | no_more_candidates | no_more_candidates | no_more_candidates |
| 几何验收 | PASS | PASS | PASS | PASS |

- 交叉统计口径：跨**所有物理高度去重**后的唯一 `(route_id_a, route_id_b)` 线路对；
  每条线路还保存了各高度交叉点数与新增高层交叉数（见各组 `summary.json` /
  `crossings_after.json`）。
- 四组均未提前耗尽 `max_groups=150` 或 3000 s 时间预算，均在候选搜索自然收敛后停止。
- L2–L5 高度仍为探索性工艺假设：几何验收为 `exploratory PASS`，
  不等同于正式制造验收。

## 目录

```
v4_c4_layer_height_ablation/
├─ baseline_crossings.json        四组共享的未抬升基线交叉缓存（同一算法口径）
├─ smoke_results.json             四档层高的少量四元组先导测试（R15/C4/圆弧限制）
├─ ablation_table.json / .md      四组对照表（含各高度交叉点数等原始数据）
├─ ablation_3d_compare.png/.svg   四组统一坐标范围与颜色映射的三维对比图
├─ ablation_run.log               四组并行运行日志
├─ A_0.25mm/  B_0.50mm/  C_0.75mm/  D_1.00mm/
│   ├─ routes_l3d.json            1024 条完整 XYZ 路线（圆弧/升降段/层高/长度）
│   ├─ lift_plans.json            每个 C4 四元组的实际抬升方案与被拒/回退记录
│   ├─ layer_stack.json           本组层高配置
│   ├─ crossings_before/after.json 交叉点与唯一交叉线路对
│   ├─ summary.json / checkpoint.json / validation.json / run.log / process.log
│   ├─ smoke/                     少量四元组先导测试
│   └─ plots/                     5 类 PNG+SVG：优化前后 XY、完整三维（统一 z 范围）、
│                                 L1–L5 分层、圆弧前提前抬升放大、交叉密集区前后对比
```

## 复现

```powershell
$env:PYTHONPATH = "...\OpticalWaveguideRouter2D"
# 先导测试（每档 2 个四元组）
& $py -m four_side_1024.v3c4.ablation --smoke --smoke-groups 2
# 四组完整实验（并行，相同预算）
& $py -m four_side_1024.v3c4.ablation --full --max-groups 150 --time-limit 3000
```

实现（`four_side_1024/v3c4/`）：
- `lift_cross.py`：交叉检测、抬升规划、四元组原子提交、真 3D 检查；
  安全窗口/过渡 footprint 均按实际 Δz 与 clearance 计算（不再硬编码 0.5 mm 配置常量）；
- `lift_cross_run.py`：单组运行、验收修复轮回退、唯一交叉对统计、动态层高着色与 3D 图；
- `ablation.py`：四组配置、共享基线缓存、并行运行、对照表与统一坐标/颜色的四联图。

未修改 V4 CSV、V4 1020 条路线数据、上一轮 0.5 mm 抬升实验输出与 V1/V2 历史结果。
