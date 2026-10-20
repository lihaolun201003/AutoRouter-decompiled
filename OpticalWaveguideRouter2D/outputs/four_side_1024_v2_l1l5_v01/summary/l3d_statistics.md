# 修正 L1–L5 物理模型统计报告（R9，自动生成）

- 生成时间（UTC）：2026-10-20T15:23:52Z
- 数据根目录：`outputs/four_side_1024_v2_l1l5_v01`
- 生成脚本：`four_side_1024/l3d/stats_l3d.py`（只读输入，仅写 summary/）

## 0. 模型修正与正式验收状态

- **正确模型**：L1 是接口布线层，同时包含两个端口行：z1 行物理高度 **0.0 mm**、z2 行 **0.5 mm**（两者 logical layer_id 均 = 1）；L2–L5 是四个额外布线层。多段 transition 合法。
- **旧模型（错误）**：`z1 = layer 0 / z2 = layer 4`，把 0.5 mm 端口行高差当作整个五层堆栈；旧 5L 结果 A=985 / B=723 **不可比**，仅作历史记录。
- **正式验收状态**：**NOT GRANTED**。L2–L5 物理高度目前为 `unconfirmed_simulation`（仿真输入），在导师确认前不能给出正式工艺验收结论；几何检查结果只能标为 exploratory。

## 1. 运行总览（primary = medium_050）

| 方案 | 层堆栈 | 阶段 | 布通/总数 | 失败 | flat-L1 基线 | 新增 | 抬升 | transitions | 3D 总长 mm | 几何验收 | 正式验收 |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| A | medium_050 | full+relayer | 963/1,024 | 61 | 943 | 20 | 44 | 117 | 156,179.288 | — | — |
| A | compact_025 | single+relayer | 962/1,024 | 62 | 943 | 19 | 43 | 115 | 155,904.960 | — | — |
| A | wide_100 | single+relayer | 963/1,024 | 61 | 943 | 20 | 44 | 117 | 156,202.851 | — | — |
| B | medium_050 | full+relayer | 621/1,024 | 403 | 515 | 106 | 130 | 298 | 116,731.501 | — | — |
| B | compact_025 | single+relayer | 611/1,024 | 413 | 515 | 96 | 120 | 268 | 113,583.241 | — | — |
| B | wide_100 | single+relayer | 611/1,024 | 413 | 515 | 96 | 120 | 265 | 113,192.032 | — | — |

### 1.1 flat-L1 基线（修正模型）

| 方案 | 布通 | 失败 | z1 行布通/失败 | z2 行布通/失败 | 与 R15-2D 参考一致 |
|---|---:|---:|---|---|---|
| A | 943 | 81 | 498/14 | 445/67 | 是 |
| B | 515 | 509 | 184/328 | 331/181 | 是 |

> 两个端口行都属于 L1：z1 row z=0.0 mm、z2 row z=0.5 mm，是**同一逻辑层 L1 的两个物理平面**；基线不继承任何旧 2.5D 结果。

## 2. 物理平面统计（按真实 z 分组，不按 logical layer id）

| 方案/栈 | 物理平面 | 真实 z mm | logical layer_id | 触及路由数 | flat 段数 | flat 总长 mm | 备注 |
|---|---|---:|---|---:|---:|---:|---|
| A/medium_050 | L1 z1 row | 0.000000 | 1 | 498 | 498 | 76,595.315 | L1 z1 row — L1 has TWO physical planes, both logical layer_id=1 |
| A/medium_050 | L1 z2 row | 0.500000 | 1 | 465 | 509 | 70,210.157 | L1 z2 row — L1 has TWO physical planes, both logical layer_id=1 |
| A/medium_050 | L2 | 1.000000 | 2 | 37 | 37 | 4,761.136 | — |
| A/medium_050 | L3 | 1.500000 | 3 | 24 | 24 | 2,494.649 | — |
| A/medium_050 | L4 | 2.000000 | 4 | 4 | 4 | 586.892 | — |
| A/medium_050 | L5 | 2.500000 | 5 | 8 | 8 | 746.893 | — |
| A/compact_025 | L1 z1 row | 0.000000 | 1 | 498 | 498 | 76,595.315 | L1 z1 row — L1 has TWO physical planes, both logical layer_id=1 |
| A/compact_025 | L1 z2 row | 0.500000 | 1 | 464 | 507 | 69,812.057 | L1 z2 row — L1 has TWO physical planes, both logical layer_id=1 |
| A/compact_025 | L2 | 0.750000 | 2 | 31 | 31 | 4,787.337 | — |
| A/compact_025 | L3 | 1.000000 | 3 | 23 | 23 | 3,040.514 | — |
| A/compact_025 | L4 | 1.250000 | 4 | 2 | 2 | 485.319 | — |
| A/compact_025 | L5 | 1.500000 | 5 | 16 | 16 | 603.415 | — |
| A/wide_100 | L1 z1 row | 0.000000 | 1 | 498 | 498 | 76,595.315 | L1 z1 row — L1 has TWO physical planes, both logical layer_id=1 |
| A/wide_100 | L1 z2 row | 0.500000 | 1 | 465 | 509 | 70,824.718 | L1 z2 row — L1 has TWO physical planes, both logical layer_id=1 |
| A/wide_100 | L2 | 1.500000 | 2 | 25 | 25 | 3,332.921 | — |
| A/wide_100 | L3 | 2.500000 | 3 | 22 | 22 | 3,040.669 | — |
| A/wide_100 | L4 | 3.500000 | 4 | 8 | 8 | 784.072 | — |
| A/wide_100 | L5 | 4.500000 | 5 | 18 | 18 | 384.752 | — |
| B/medium_050 | L1 z1 row | 0.000000 | 1 | 211 | 238 | 33,689.797 | L1 z1 row — L1 has TWO physical planes, both logical layer_id=1 |
| B/medium_050 | L1 z2 row | 0.500000 | 1 | 410 | 513 | 55,142.708 | L1 z2 row — L1 has TWO physical planes, both logical layer_id=1 |
| B/medium_050 | L2 | 1.000000 | 2 | 57 | 57 | 6,718.956 | — |
| B/medium_050 | L3 | 1.500000 | 3 | 39 | 39 | 5,095.177 | — |
| B/medium_050 | L4 | 2.000000 | 4 | 41 | 41 | 7,996.119 | — |
| B/medium_050 | L5 | 2.500000 | 5 | 31 | 31 | 5,635.104 | — |
| B/compact_025 | L1 z1 row | 0.000000 | 1 | 205 | 226 | 33,089.043 | L1 z1 row — L1 has TWO physical planes, both logical layer_id=1 |
| B/compact_025 | L1 z2 row | 0.500000 | 1 | 406 | 505 | 53,971.374 | L1 z2 row — L1 has TWO physical planes, both logical layer_id=1 |
| B/compact_025 | L2 | 0.750000 | 2 | 71 | 71 | 12,693.792 | — |
| B/compact_025 | L3 | 1.000000 | 3 | 32 | 32 | 4,299.670 | — |
| B/compact_025 | L4 | 1.250000 | 4 | 20 | 20 | 4,248.812 | — |
| B/compact_025 | L5 | 1.500000 | 5 | 25 | 25 | 3,807.718 | — |
| B/wide_100 | L1 z1 row | 0.000000 | 1 | 207 | 230 | 33,177.947 | L1 z1 row — L1 has TWO physical planes, both logical layer_id=1 |
| B/wide_100 | L1 z2 row | 0.500000 | 1 | 404 | 501 | 54,055.632 | L1 z2 row — L1 has TWO physical planes, both logical layer_id=1 |
| B/wide_100 | L2 | 1.500000 | 2 | 33 | 33 | 5,468.063 | — |
| B/wide_100 | L3 | 2.500000 | 3 | 63 | 63 | 11,022.764 | — |
| B/wide_100 | L4 | 3.500000 | 4 | 25 | 25 | 4,298.249 | — |
| B/wide_100 | L5 | 4.500000 | 5 | 24 | 24 | 2,129.080 | — |

- **L1 双物理平面检查（A）**：L1 在物理平面表中出现 2 次，z = [0.0, 0.5] mm，行 = ['z1', 'z2']，两者 logical layer_id 均为 1（同一逻辑接口层的两个真实高度）。
- **L1 双物理平面检查（B）**：L1 在物理平面表中出现 2 次，z = [0.0, 0.5] mm，行 = ['z1', 'z2']，两者 logical layer_id 均为 1（同一逻辑接口层的两个真实高度）。

## 3. 逻辑层与层序列统计

| 方案/栈 | 逻辑层 | 物理 z mm / 行 | 触及路由数 | flat 段数 | flat 总长 mm | transition 端点 |
|---|---|---|---:|---:|---:|---:|
| A/medium_050 | L1 | rows z1=0.0 / z2=0.5 | 963 | 1,007 | 146,805.472 | 88 |
| A/medium_050 | L2 | 1.000000 | 37 | 37 | 4,761.136 | 74 |
| A/medium_050 | L3 | 1.500000 | 24 | 24 | 2,494.649 | 48 |
| A/medium_050 | L4 | 2.000000 | 4 | 4 | 586.892 | 8 |
| A/medium_050 | L5 | 2.500000 | 8 | 8 | 746.893 | 16 |
| B/medium_050 | L1 | rows z1=0.0 / z2=0.5 | 621 | 751 | 88,832.505 | 260 |
| B/medium_050 | L2 | 1.000000 | 57 | 57 | 6,718.956 | 114 |
| B/medium_050 | L3 | 1.500000 | 39 | 39 | 5,095.177 | 78 |
| B/medium_050 | L4 | 2.000000 | 41 | 41 | 7,996.119 | 82 |
| B/medium_050 | L5 | 2.500000 | 31 | 31 | 5,635.104 | 62 |

### 3.1 直方图（primary）

| 方案 | layers-used 直方图 | layer sequence 直方图 | transition 数直方图 |
|---|---|---|---|
| A | {'1': 919, '1,2': 14, '1,2,3': 15, '1,2,3,5': 4, '1,2,4': 1, '1,2,4,5': 1, '1,2,5': 2, '1,3': 4, '1,3,4': 1, '1,4': 1, '1,5': 1} | 1:919; 1->2->1:14; 1->2->3->1:14; 1->2->3->5->1:2; 1->2->4->5->1:1; 1->2->5->1:1; ...(14 keys) | {'0': 919, '2': 20, '3': 19, '4+': 5} |
| B | {'1': 491, '1,2': 29, '1,2,3': 16, '1,2,3,5': 5, '1,2,4': 5, '1,2,4,5': 2, '1,3': 16, '1,3,4': 1, '1,3,5': 1, '1,4': 32, '1,4,5': 1, '1,5': 22} | 1:491; 1->2->1:29; 1->2->3->1:11; 1->2->3->5->1:2; 1->2->4->1:2; 1->3->1:16; ...(15 keys) | {'0': 491, '2': 99, '3': 24, '4+': 7} |

### 3.2 transition 层对 / dz 直方图（primary）

| 方案 | from→to | dz mm | 次数 | θ 总计° | footprint 总计 mm | 弧长总计 mm | 半径 mm |
|---|---|---:|---:|---:|---:|---:|---|
| A | L1→L2 | 0.500000 | 32 | 335.210 | 174.539 | 175.516 | [15.0] |
| A | L1→L3 | 1.000000 | 6 | 89.011 | 46.087 | 46.606 | [15.0] |
| A | L1→L4 | 1.500000 | 2 | 36.390 | 18.735 | 19.054 | [15.0] |
| A | L1→L5 | 2.000000 | 4 | 84.158 | 43.081 | 44.065 | [15.0] |
| A | L2→L1 | -0.500000 | 19 | 199.031 | 103.633 | 104.212 | [15.0] |
| A | L2→L3 | 0.500000 | 16 | 167.605 | 87.270 | 87.758 | [15.0] |
| A | L2→L4 | 1.000000 | 1 | 14.835 | 7.681 | 7.768 | [15.0] |
| A | L2→L5 | 1.500000 | 1 | 18.195 | 9.367 | 9.527 | [15.0] |
| A | L3→L1 | -1.000000 | 18 | 267.032 | 138.261 | 139.818 | [15.0] |
| A | L3→L2 | -0.500000 | 3 | 31.426 | 16.363 | 16.455 | [15.0] |
| A | L3→L4 | 0.500000 | 1 | 10.475 | 5.454 | 5.485 | [15.0] |
| A | L3→L5 | 1.000000 | 2 | 29.670 | 15.362 | 15.535 | [15.0] |
| A | L4→L1 | -1.500000 | 2 | 36.390 | 18.735 | 19.054 | [15.0] |
| A | L4→L2 | -1.000000 | 1 | 14.835 | 7.681 | 7.768 | [15.0] |
| A | L4→L5 | 0.500000 | 1 | 10.475 | 5.454 | 5.485 | [15.0] |
| A | L5→L1 | -2.000000 | 5 | 105.197 | 53.852 | 55.081 | [15.0] |
| A | L5→L2 | -1.500000 | 1 | 18.195 | 9.367 | 9.527 | [15.0] |
| A | L5→L3 | -1.000000 | 2 | 29.670 | 15.362 | 15.535 | [15.0] |
| B | L1→L2 | 0.500000 | 35 | 366.636 | 190.902 | 191.970 | [15.0] |
| B | L1→L2 | 1.000000 | 9 | 133.516 | 69.130 | 69.909 | [15.0] |
| B | L1→L3 | 1.000000 | 16 | 237.362 | 122.898 | 124.282 | [15.0] |
| B | L1→L3 | 1.500000 | 6 | 109.169 | 56.205 | 57.161 | [15.0] |
| B | L1→L4 | 1.500000 | 31 | 564.041 | 290.392 | 295.331 | [15.0] |
| B | L1→L4 | 2.000000 | 6 | 126.237 | 64.622 | 66.097 | [15.0] |
| B | L1→L5 | 2.000000 | 21 | 441.829 | 226.177 | 231.341 | [15.0] |
| B | L1→L5 | 2.500000 | 6 | 141.339 | 71.937 | 74.005 | [15.0] |
| B | L2→L1 | -1.000000 | 8 | 118.681 | 61.449 | 62.141 | [15.0] |
| B | L2→L1 | -0.500000 | 34 | 356.161 | 185.448 | 186.485 | [15.0] |
| B | L2→L3 | 0.500000 | 13 | 136.179 | 70.907 | 71.303 | [15.0] |
| B | L2→L4 | 1.000000 | 2 | 29.670 | 15.362 | 15.535 | [15.0] |
| B | L3→L1 | -1.500000 | 7 | 127.364 | 65.572 | 66.688 | [15.0] |
| B | L3→L1 | -1.000000 | 21 | 311.537 | 161.304 | 163.121 | [15.0] |
| B | L3→L2 | -0.500000 | 8 | 83.803 | 43.635 | 43.879 | [15.0] |
| B | L3→L5 | 1.000000 | 3 | 44.505 | 23.043 | 23.303 | [15.0] |
| B | L4→L1 | -2.000000 | 5 | 105.197 | 53.852 | 55.081 | [15.0] |
| B | L4→L1 | -1.500000 | 29 | 527.651 | 271.657 | 276.278 | [15.0] |
| B | L4→L2 | -1.000000 | 5 | 74.176 | 38.406 | 38.838 | [15.0] |
| B | L4→L3 | -0.500000 | 1 | 10.475 | 5.454 | 5.485 | [15.0] |
| B | L4→L5 | 0.500000 | 1 | 10.475 | 5.454 | 5.485 | [15.0] |
| B | L5→L1 | -2.500000 | 7 | 164.895 | 83.927 | 86.339 | [15.0] |
| B | L5→L1 | -2.000000 | 19 | 399.750 | 204.636 | 209.309 | [15.0] |
| B | L5→L3 | -1.000000 | 3 | 44.505 | 23.043 | 23.303 | [15.0] |
| B | L5→L4 | -0.500000 | 2 | 20.951 | 10.909 | 10.970 | [15.0] |

## 4. 长度与 z_span

| 方案/栈 | XY 总长 mm | 3D 总长 mm | flat 总长 mm | transition 总长 mm | 平均 3D 长 mm | z_span 分布 |
|---|---:|---:|---:|---:|---:|---|
| A/medium_050 | 156,171.328 | 156,179.288 | 155,395.042 | 784.246 | 162.180 | {'0.000000': 919, '0.500000': 14, '1.000000': 19, '1.500000': 3, '2.000000': 8} |
| A/compact_025 | 155,901.541 | 155,904.960 | 155,323.957 | 581.004 | 162.063 | {'0.000000': 919, '0.250000': 14, '0.500000': 12, '0.750000': 1, '1.000000': 16} |
| A/wide_100 | 156,171.328 | 156,202.851 | 154,962.448 | 1,240.403 | 162.204 | {'0.000000': 919, '1.000000': 12, '2.000000': 10, '3.000000': 4, '4.000000': 18} |
| B/medium_050 | 116,694.187 | 116,731.501 | 114,277.862 | 2,453.639 | 187.973 | {'0.000000': 491, '0.500000': 22, '1.000000': 33, '1.500000': 38, '2.000000': 29, '2.500000': 8} |
| B/compact_025 | 113,572.241 | 113,583.241 | 112,110.409 | 1,472.832 | 185.897 | {'0.000000': 491, '0.250000': 45, '0.500000': 23, '0.750000': 18, '1.000000': 24, '1.250000': 4, '1.500000': 6} |
| B/wide_100 | 113,108.320 | 113,192.032 | 110,151.735 | 3,040.297 | 185.257 | {'0.000000': 491, '1.000000': 13, '1.500000': 8, '2.000000': 47, '2.500000': 7, '3.000000': 17, '3.500000': 4, '4.000000': 20, '4.500000': 4} |

- flat 2D 几何（A/medium_050）：弧数 1,971，半径分布 {'15.000000': 1971}，全部 R15=是。
- flat 2D 几何（A/compact_025）：弧数 1,968，半径分布 {'15.000000': 1968}，全部 R15=是。
- flat 2D 几何（A/wide_100）：弧数 1,971，半径分布 {'15.000000': 1971}，全部 R15=是。
- flat 2D 几何（B/medium_050）：弧数 1,618，半径分布 {'15.000000': 1618}，全部 R15=是。
- flat 2D 几何（B/compact_025）：弧数 1,548，半径分布 {'15.000000': 1548}，全部 R15=是。
- flat 2D 几何（B/wide_100）：弧数 1,496，半径分布 {'15.000000': 1496}，全部 R15=是。

## 5. 独立 3D 验收摘要（exploratory only）

| 方案/栈 | 报告 | 几何通过 | exploratory | formal acceptance | 最小 3D 间距 mm | 最小曲率半径 mm | 违规计数 |
|---|---|---|---|---|---:|---:|---|
| A/medium_050 | — | — | — | — | — | — | 全部 0 |
| A/compact_025 | — | — | — | — | — | — | 全部 0 |
| A/wide_100 | — | — | — | — | — | — | 全部 0 |
| B/medium_050 | — | — | — | — | — | — | 全部 0 |
| B/compact_025 | — | — | — | — | — | — | 全部 0 |
| B/wide_100 | — | — | — | — | — | — | 全部 0 |

> **正式验收：NOT GRANTED。** L2-L5 physical heights are unconfirmed_simulation simulation inputs; formal process acceptance is refused for every stack

## 6. 失败分析

| 方案/栈 | 记录失败 | 无 2D 候选(记录) | 3D 无法放置(记录) | transition 放置不可行(rejected) | router: 无2D候选 / 3D阻塞 / 未尝试 | 其他记录原因 | 分平面 |
|---|---:|---:|---:|---:|---|---|---|
| A/medium_050 | 61 | 2 | 59 | 342 | 2 / 59 / -118 | — | {'z1': {'unplaceable_in_3d': 14}, 'z2': {'unplaceable_in_3d': 45, 'no_2d_candidate': 2}} |
| A/compact_025 | 62 | 2 | 60 | 132 | 2 / 60 / -60 | — | {'z1': {'unplaceable_in_3d': 14}, 'z2': {'unplaceable_in_3d': 46, 'no_2d_candidate': 2}} |
| A/wide_100 | 61 | 2 | 59 | 189 | 2 / 59 / -59 | — | {'z1': {'unplaceable_in_3d': 14}, 'z2': {'unplaceable_in_3d': 45, 'no_2d_candidate': 2}} |
| B/medium_050 | 403 | 78 | 325 | 5,894 | 78 / 325 / -662 | — | {'z1': {'unplaceable_in_3d': 225, 'no_2d_candidate': 76}, 'z2': {'unplaceable_in_3d': 100, 'no_2d_candidate': 2}} |
| B/compact_025 | 413 | 78 | 335 | 1,734 | 78 / 335 / -336 | — | {'z1': {'unplaceable_in_3d': 231, 'no_2d_candidate': 76}, 'z2': {'unplaceable_in_3d': 104, 'no_2d_candidate': 2}} |
| B/wide_100 | 413 | 78 | 335 | 5,068 | 78 / 335 / -339 | — | {'z1': {'unplaceable_in_3d': 229, 'no_2d_candidate': 76}, 'z2': {'unplaceable_in_3d': 106, 'no_2d_candidate': 2}} |

> 口径：记录中的 `unplaceable_in_3d` 包含“尚未尝试”的路线；router 统计区分 attempted / unattempted，并记录 `transition_placement_infeasible`（S 曲线无法放到 2D 路径上）。

## 7. 损耗参数口径（不输出总损耗结论）

| 参数 | 值 | 状态 | 已标定 | 说明 |
|---|---|---|---|---|
| propagation_loss | 0.05 dB/cm | experimental_convention_not_measured | False | length-only experiment convention; not a measured glass value |
| bend_loss | — | unknown_uncalibrated | False | no calibrated glass bend-loss function; R=15 mm is a geometry constraint only |
| crossing_loss | — | unknown_uncalibrated | False | single-layer crossing optical feasibility not confirmed; crossing counts are geometric only |
| interlayer_loss | — | unknown_uncalibrated | False | multi-layer transitions and interlayer propagation effects are not calibrated |

> **本轮不输出总损耗结论。** 传播损耗 0.05 dB/cm 为实验约定（非实测）；弯曲 / 交叉 / 层间损耗均 `unknown_uncalibrated`。

## 8. 警告

- L3D validation reports not found under outputs/four_side_1024_v2_l1l5_v01/validation (validation block null)
- A/compact_025: independent L3D validation report not found (validation block null)
- layer stack provenance is unconfirmed_simulation: formal process acceptance is NOT granted (heights are simulation inputs)
- A/medium_050: independent L3D validation report not found (validation block null)
- layer stack provenance is unconfirmed_simulation: formal process acceptance is NOT granted (heights are simulation inputs)
- A/wide_100: independent L3D validation report not found (validation block null)
- layer stack provenance is unconfirmed_simulation: formal process acceptance is NOT granted (heights are simulation inputs)
- B/compact_025: independent L3D validation report not found (validation block null)
- layer stack provenance is unconfirmed_simulation: formal process acceptance is NOT granted (heights are simulation inputs)
- B/medium_050: independent L3D validation report not found (validation block null)
- layer stack provenance is unconfirmed_simulation: formal process acceptance is NOT granted (heights are simulation inputs)
- B/wide_100: independent L3D validation report not found (validation block null)
- layer stack provenance is unconfirmed_simulation: formal process acceptance is NOT granted (heights are simulation inputs)

