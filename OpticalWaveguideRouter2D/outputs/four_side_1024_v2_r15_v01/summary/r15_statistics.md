# R15 轮统计报告（自动生成）

- 生成时间（UTC）：2026-10-20T08:58:33Z
- 数据根目录：`outputs/four_side_1024_v2_r15_v01`
- 生成脚本：`four_side_1024/r15/stats_r15.py`（只读输入，不修改任何路由数据）
- 工艺要求：所有平面弯曲与 3D 升降弯曲 **R = 15.0 mm**（R15 本轮要求；R40 结果不在本文件混合）

## 1. 数据状态

| 输入 | 状态 |
|---|---|
| planes/V2/A/z1 | 已生成 |
| planes/V2/A/z2 | 已生成 |
| combined/V2/A | 已生成 |
| planes/V2/B/z1 | 已生成 |
| planes/V2/B/z2 | 已生成 |
| combined/V2/B | 已生成 |
| 25d/schemeA/layers5 | 已生成 |
| 25d validation A | 已生成 |
| 25d/schemeB/layers5 | 已生成 |
| 25d validation B | 已生成 |

> 警告 2 条（详见 `r15_statistics.json` 的 `warnings` 字段）：
> - 3D A: 4 validation reports matched; using outputs/four_side_1024_v2_r15_v01/25d/validation/A/layers5.json
> - 3D B: 4 validation reports matched; using outputs/four_side_1024_v2_r15_v01/25d/validation/B/layers5.json

## 2. 二维（R15）统计

### 2.1 平面汇总（由图元重算）

| 方案 | 平面 | 布通/总数 | 失败 | 总长 mm | 平均长 mm | 直线长 mm | 弧长 mm | 弧数 | 90°弧 | 短S弧 | 最小半径 mm | 同层交叉 | 非R15弧数 | R15 验收 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A | z1 | 498/512 | 14 | 76,595.315 | 153.806 | 65,579.983 | 11,015.332 | 762 | 0 | 762 | 15.000000 | 69,072 | 0 | PASS |
| A | z2 | 445/512 | 67 | 73,004.217 | 164.054 | 52,106.106 | 20,898.112 | 1,155 | 645 | 510 | 15.000000 | 67,110 | 0 | PASS |
| B | z1 | 184/512 | 328 | 33,038.643 | 179.558 | 25,970.060 | 7,068.583 | 300 | 300 | 0 | 15.000000 | 13,342 | 0 | PASS |
| B | z2 | 331/512 | 181 | 55,808.746 | 168.606 | 35,993.150 | 19,815.596 | 841 | 841 | 0 | 15.000000 | 40,842 | 0 | PASS |

- 2D 独立 strict 验收：—（outputs/four_side_1024_v2_r15_v01/final_validation.json）
- 逐波导 2D 明细见 `r15_per_waveguide_2d.csv`（按 4 个平面各 512 条列出，含失败记录；组合 1024 = 两平面并集，不重复输出）。

### 2.2 组合 1024 通道（A/B 标签）

| 方案 | 布通/总数 | 失败 | 总长 mm | 总弧数 | 90°弧 | 短S弧 | 同层交叉(两平面和) | combined 验收 | 说明 |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| A | 943/1,024 | 81 | 149,599.532 | 1,917 | 645 | 1,272 | 136,182 | PASS | combined routes_1024.json |
| B | 515/1,024 | 509 | 88,847.389 | 1,141 | 1,141 | 0 | 54,184 | PASS | combined routes_1024.json |

### 2.3 弧半径 / 转角分布

| 方案 | 标签范围 | 半径分布 | 90° 弧 | 短S弧 | 短S 平均转角° | 短S 弧长 mm | 90° 弧长 mm |
|---|---|---|---:|---:|---:|---:|---:|
| A | 15.000000 – 15.000000 | {'15.000000': 1917} | 645 | 1,272 | 50.197 | 16,715.989 | 15,197.454 |
| B | 15.000000 – 15.000000 | {'15.000000': 1141} | 1,141 | 0 | — | 0.000 | 26,884.179 |

> 2.3 的几何来源：方案 A: combined routes_1024.json；方案 B: combined routes_1024.json

## 3. 三维（R15 五层 2.5D）统计

| 方案 | 布通 | 失败 | 抬升 | 升降次数 | flat 长 mm | transition 长 mm | 总长 mm | theta 总计° | footprint 总计 mm | transition 弧长总计 mm | 半径分布 | 验收 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| A | 985 | 39 | 42 | 84 | 159,878.158 | 316.074 | 160,194.232 | 603.657 | 315.095 | 316.074 | {'15.000000': 84} | PASS |
| B | 723 | 301 | 208 | 416 | 134,923.516 | 1,538.718 | 136,462.234 | 2,938.735 | 1,534.232 | 1,538.718 | {'15.000000': 416} | PASS |

### 3.1 逐层 flat 段与旅行层分布

| 方案 | 每层 flat 段 | travel layer 分布 | 每路线 transition 数分布 |
|---|---|---|---|
| A | {'0': 526, '1': 32, '2': 6, '3': 4, '4': 501} | {'1': 32, '2': 6, '3': 4} | {0: 943, 2: 42} |
| B | {'0': 480, '1': 69, '2': 66, '3': 73, '4': 451} | {'1': 69, '2': 66, '3': 73} | {0: 515, 2: 208} |

### 3.2 三维独立验收（validate_r15 / fsd25d.validate25d，R15 概况）

| 方案 | 验收 | 同层交叉(各层和) | 各层交叉 | 最小 3D 距离 mm | 最小曲率半径 mm | 曲率达标(≥14.985) | 违规计数 |
|---|---|---:|---|---:|---:|---|---|
| A | PASS | 137,081 | {'0': 69072, '1': 424, '2': 48, '3': 16, '4': 67521} | 0.080295032 | 14.999999963 | 是 | 全部 0 |
| B | PASS | 63,816 | {'0': 13724, '1': 2684, '2': 2881, '3': 3663, '4': 40864} | 0.080000000 | 14.999999966 | 是 | 全部 0 |

## 4. 损耗参数口径（不输出总损耗结论）

- 半径要求：R = 15.0 mm；检测到 process radius = 15.000000 mm；达标 = 是

| 参数 | 值 | 状态 | 已标定 | 说明 |
|---|---|---|---|---|
| propagation_loss | 0.05 dB/cm | experimental_convention_not_measured | False | length-only experiment convention; not a measured glass value |
| bend_loss | — | unknown_uncalibrated | False | no calibrated femtosecond-laser-written glass bend-loss function; R=15 mm is a geometry constraint only, not a measured loss value |
| crossing_loss | — | unknown_uncalibrated | False | single-layer crossing optical feasibility not confirmed; crossing counts are geometric metrics only |
| interlayer_effect | — | unknown_uncalibrated | False | effect of the two 3D elevation S-curves / interlayer travel on loss is not calibrated |

> **本轮不输出总损耗结论。** 弯曲损耗、交叉损耗、层间影响均为 `unknown_uncalibrated`；质量上唯一的已知参数是传播损耗实验约定 `0.05 dB/cm`（非实测标定）。若需要损耗预算，必须先由实验标定 弯曲/交叉/层间系数。

