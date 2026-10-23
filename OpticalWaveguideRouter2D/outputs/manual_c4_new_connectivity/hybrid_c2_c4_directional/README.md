# Hybrid C2/C4 Directional Layer Routing（H / V）

基于 commit `6ef0679` 的 Structured A 结果，开展"按方向分层"的三维布线实验：把
z1 的 264 条对边连接按端口方向拆成横向与纵向两组，让两组处于不同物理高度，从而
消除横纵直线在同一高度上的十字交叉；z1 只要求 **C2（180°旋转）** 对称，z2 保持
**严格 C4** 且上一轮已成功的 U 形线束固定不动。

## 方向拆分（由端口 side 判定，不按 route_id 猜测）

| 组 | z1 横向 E↔W | z1 纵向 N↔S | 目标 |
|---|---:|---:|---|
| **H** | 132 条 = 66 个 C2 二元组 | 132 条 = 66 个 C2 二元组 | 横向全部优先升 **L2 (1.0 mm)**，纵向留 **L1-z1 (0 mm)** |
| **V** | 132 条 = 66 个 C2 二元组 | 132 条 = 66 个 C2 二元组 | 纵向全部优先升 L2，横向留 L1-z1（反向对照） |

每个 z1 C4 四元组拆成两个 C2 二元组：`{phase0, phase2}`（纵向）与
`{phase1, phase3}`（横向）。C2 二元组的两条路线是严格 180°旋转关系，升降窗口
参数 `(a_in, a_out)` 在旋转下保持一致（反向成员交换入口/出口）。

固定不变（严格 C4）：
- z2 U 线束：L3 = group 20–35 + 144–159（128 条），L4 = 160–175（64 条），
  L5 = 176–191（64 条）——与 Structured A 逐字段相同；
- z2 对边 8 条保持 L2；496 条邻边保持各自接口层平铺；
- 1024 连接 / 2048 端口 / 不交换物理排。

## 方法

1. 从 Structured A 的 1024 条合法路线出发，固定 U、z2 对边、邻边；
2. 把 z1 对边按方向拆成 66 + 66 个 C2 二元组；
3. 对每个 C2 二元组做 3D 可行性扫描（每对临时移出自身 z=0 平铺路线），目标方向
   逐对抬升到 L2：`端口 → base 直线 → S 上升 → L2 直线 → S 下降 → base 直线 → 端口`，
   升降窗口 `(a_in, a_out)` 在同一 C2 二元组内共享；
4. 逐对装配（按最早可行窗口排序、原子提交），C2 对称性保持；
5. 完整 XYZ 碰撞检查 + 权威 `l3d.validate_payload` 验收（identity 用 phase2_2d，
   连接表未变）；另做混合 C2/C4 独立验收。

## 结果

| 指标 | H（横向升 L2） | V（纵向升 L2） | 旧 Structured A | 旧 Spatial U-bundle |
|---|---:|---:|---:|---:|
| 总布通数 | **1024/1024** | **1024/1024** | 1024/1024 | 1024/1024 |
| C2 二元组抬升数 | **64/66**（2 组失败保留接口层） | **64/66** | — | — |
| z1 横纵同层交叉对 | **7032** | 7032 | 10928 | — |
| z=0 交叉对（统一 fslw 审计口径） | **11952** | 11952 | 17576 | — |
| L2 交叉对 | **0** | 0 | 1000 | — |
| 全局唯一交叉对 | **12960** | 12960 | 19584 | 12824 |
| 升降次数 | **784** | 784 | 944 | 824 |
| 三维总长 (mm) | **98,019.93** | 98,019.93 | 98,033.77 | 98,539.01 |
| 最小三维净空 (mm) | **0.0917** | 0.0917 | 0.0917 | 0.0832 |
| 权威 3D 验收 | exploratory PASS，9 类 counts 全 0 | 同上 | PASS | PASS |
| 层计数 L1-z1/L1-z2/L2/L3/L4/L5 | 512/512/136/128/64/64 | 512/512/136/128/64/64 | 512/512/216/128/64/64 | 512/512/252/80/68/12 |

注：H/V 的指标完全相同，这是由 A 的布局严格 C4 对称决定的——横向抬升与纵向抬升
互为 90°旋转等价方案；两者都独立保存、独立验收。

### 交叉削减（相对 Structured A，统一 fslw 审计口径）

- z1 横纵同层交叉对：**10928 → 7032（−3896，−35.7%）**；其中 z=0 的横纵交叉
  9928 → 7032，L2 的横纵交叉 1000 → 0。
- z=0 总交叉对：**17576 → 11952（−5624，−32.0%）**。
- 全局唯一交叉对：**19584 → 12960（−6624，−33.8%）**（旧 Spatial 为 12824，本轮
  12960 略高 136 对：Spatial 的 U/对边层分配不同；本轮以"方向分层正确性/结构规整"
  为优先）。

剩余的 7032 对"横纵同层交叉"全部发生在 **z=0 抬升方向的 base 直线段**（升到 L2 之前
/ 降回之后的那段保留在接口层），不是目标层平面上的交叉；详见证交叉分析
`crossing_analysis.json`。

## 失败与主要瓶颈

1. **2 个 C2 二元组无法抬升（保留 L1-z1）**：group 2 与 group 3 的横向对（H）/
   纵向对（V）在固定世界下对称与不对称窗口均无可行 (a_in, a_out)，原因写入
   `c2_pair_assignment.json` 与 `summary.c2_failures`。这与 Structured A 中这两个
   组作为例外的结论一致。
2. **34 个 C2 二元组只能使用"深升降窗口"（主要瓶颈）**：z2 接口层的相邻路线
   （z=0.5）与目标方向 line 在**同排并行**（parallel shadow）；R15 + dz=1.0 的
   S 升降足印为 **7.68 mm**，而横向 line 到端口后的影子段起始距离通常小于足印长度，
   无法"在进入密集交叉区之前完成上升"。因此这些组的最小可行 `a_in` 在 40–60 mm
   （只能把升降放到影子之外/中央），导致 base 直线段变长、剩余 z=0 横纵交叉增加。
   证据：`_work/shadow_bottleneck_analysis.json`（H/V 各 34 对，32 对为
   parallel_shadow、2 对无可行参数）。
3. 理论上"进入密集区前完成上升"对上/下升降都受 R15 + dz=1.0 足印限制：横向对边线
   从 W/E 边进入后，到第一条纵向 line 的距离约 7.6 mm，已略小于 S 升降足印 7.68 mm；
   若要在所有点都保持 0.08 mm 净空，只能依赖影子线路协同重路由（本轮未实施，
   作为主要后续工作记录）。

## 目录与文件

```
hybrid_c2_c4_directional/
├── README.md
├── comparison_table.json/.md        H/V/旧 Structured A/旧 Spatial 对照
├── H/  V/                           两组独立结果
│   ├── routes_1024.json             完整 1024 条 XYZ
│   ├── c2_pair_assignment.json      66 个 C2 二元组分层结果、参数、升降起止、失败原因
│   ├── crossing_analysis.json       原始 z=0 交叉来源 / 削减量 / 新交叉分解
│   ├── validation.json              权威 3D 验收报告
│   ├── summary.json                 指标汇总（含 figures/delivery）
│   ├── figures/                     13 组 PNG+SVG：
│   │    01_before_3d, 02_after_3d, 03_L1_z1…08_L5,
│   │    09_z1_horizontal, 10_z1_vertical, 11_z1_direction_split,
│   │    12_opposite_only_3d, 13_dense_region_zoom
│   └── READY / ARTEFACTS_READY
├── _work/                           可行性扫描、H/V 世界、shadow_bottleneck_analysis、
│                                    A 方向交叉基线
└── verification/                    混合 C2/C4 独立验收脚本与报告（独立验收员产出）
```

## 复现

```powershell
$py = ".venv\Scripts\python.exe"
$env:PYTHONPATH = (Get-Location).Path
# 1) C2 二元组可行性扫描（H/V；约 2 分钟，多进程）
python <scan_pairs.py> H   # 生成 _work/H_feasibility.json
python <scan_pairs.py> V
# 2) 装配 + 权威验收 + 交叉分析
& $py -m four_side_1024.manual_c4.run_hybrid_c2_c4 --variant H
& $py -m four_side_1024.manual_c4.run_hybrid_c2_c4 --variant V
# 3) 图与对照表
& $py -m four_side_1024.manual_c4.hybrid_c2_c4_plots --variant H
& $py -m four_side_1024.manual_c4.hybrid_c2_c4_plots --variant V
& $py -m four_side_1024.manual_c4.hybrid_comparison
```

## 约束口径

板面 150×150 mm；R=15 mm；宽 0.05 mm；非豁免最小中心线净空 0.08 mm；接口高度
z1=0 / z2=0.5；L2/L3/L4/L5=1.0/1.5/2.0/2.5 mm；端口坐标/入射方向固定；z1 允许
C2（180°旋转）、z2 严格 C4（90°旋转）；升降仅在二维直线段、每条 ≤1 升 1 降；
完整 XYZ 碰撞/曲率/净空验收。层高为探索性参数，3D 验收为 exploratory PASS
（formal_acceptance=false），不代表制造工艺正式验收。
