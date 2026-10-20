# 任务 5.4：V2 z2 平面候选预算 200/400/800/1600 对照实验与候选覆盖分析

> 全部数字由 `four_side_1024/v2opt/sweep_analysis.py` 从真实产物文件重算得出，没有任何手工填写值。

## 1. 实验设置

| 项目 | 值 |
|---|---|
| 拓扑 / 平面 | V2 / z2 |
| 冻结 BASE 布局（历史 C/z2） | 206 / 512 已布通（待测试 306 条） |
| 历史 pair 分布（成功/失败） | NS 0/0；EW 0/0；EN 64/64；ES 37/91；SW 43/85；NW 62/66 |
| 历史 routes.json | `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\outputs\four_side_1024_fslw_R40_gap30_abcd\planes\V2\C\z2\routes.json` |
| 测试方式 | 单路线独立插入测试（`parallel_sweep`）：每个失败路线独立在冻结布局上尝试，找到的候选 **不提交**、不改变布局 |
| 候选来源 | `candext` 扩展 D56 候选库（L / TURN_S / SHIFT_TURN / Z3 / LEFT / Z5 / DOWN_LOOP，同一 primitive 集） |
| 评估预算 | 200 / 400 / 800 / 1600 |
| 并行度 | 10 个进程 |
| 合法性判定 | 冻结的严格 D56 精确索引 `D56Index.evaluate`（`crossing_policy=strict`） |

复现命令（项目根 `OpticalWaveguideRouter2D/`）：

```powershell
.venv\Scripts\python.exe -m four_side_1024.v2opt.pipeline sweep --plane z2 --budgets 200,400,800,1600 --workers 10
.venv\Scripts\python.exe -m four_side_1024.v2opt.sweep_analysis
```

说明：sweep 每个预算档独立重跑 306 条失败路线；`sweep_analysis.py --coverage-only` 可单独重算 128 条 corner 路线的全候选队列覆盖（多进程，结果缓存于 `coverage_128_corner_routes.json`）。

> 运行备注：本次 sweep 进程结束时退出码为 1，原因是 `pipeline.py` 的 `main()` 在 `finally` 中先 `handle.close()` 再调用 `log(f'log written ...')`（写已关闭的日志句柄）触发 `ValueError`。该异常发生在 **四档预算全部完成并写出产物之后**，四个 sweep JSON 均已校验完整（本报告第 2 节自检全部通过），不影响实验结果；本脚本未修改任何共享模块。

## 2. 自检（数据一致性）

| 检查项 | 结果 |
|---|---|
| 四档 found 集合逐档嵌套 | PASS |
| summary.found == len(found_route_ids) | PASS |
| 四档 found 并集 == 累计救回路线数 | 62 / 62 |
| summary.evaluated == sum(逐路线 evaluated) | PASS |
| evaluated==budget 但无预算标记（候选队列恰为 budget 条的边界情形，仍按"当前布局阻挡"归类） | 1 |
| coverage 缓存路线数 | 128 / 128 |
| coverage 与 sweep found 交叉校验不一致数 | 0 |
| coverage 0 生成集合 == sweep 各档 no_candidate_generated 集合 | PASS |
| empty-layout 0 生成集合 == base-layout 0 生成集合 | PASS |

## 3. 预算阶梯结果

| 预算 | found | 边际新增 | 累计 found | 累计救回率 | evaluated 总数 | evaluated/路线 | 耗时 (s) | 每条边际新增消耗的评估数 |
|---|---|---|---|---|---|---|---|---|
| 200 | 22 | 22 | 22 | 7.19% | 36,057 | 117.8 | 106.1 | 1,639 |
| 400 | 42 | 20 | 42 | 13.73% | 58,686 | 191.8 | 170.8 | 1,131 |
| 800 | 62 | 20 | 62 | 20.26% | 81,821 | 267.4 | 197.5 | 1,157 |
| 1600 | 62 | 0 | 62 | 20.26% | 90,851 | 296.9 | 194.7 | - |

说明：`evaluated` 是真实执行的候选合法性评估次数之和；它小于 `预算 × 306` 有两个原因：部分路线的扩展候选队列本身短于预算（队列耗尽即结束），以及部分路线在命中合法候选后提前结束。

### 3.1 边际收益结论

- 预算 200 即可救回 **22** 条（占 306 条待测路线的 7.2%）。
- 200→1600 累计只多救回 **40** 条（22 → 62），边际收益快速衰减：200→400 新增 20，400→800 新增 20，800→1600 新增 0。
- 全部 62 条成功路线的成功候选在候选队列中的位置：中位数 234，最小 52，最大 778；其中 22 条在队列前 200 个候选内即可命中。
- 评估耗时：200 档 106.1s → 1600 档 194.7s（evaluated 36,057 → 90,851）。
- 性价比：400 档已拿到最终累计收益的 67.7%（42/62）；800→1600 无任何新增，候选预算在 800 以上已饱和。

### 3.2 各档新增救回路线 ID

- **预算 200**（新增 22 条）：`519-520, 527-528, 535-536, 751-753, 757-759, 761, 766-767, 877-880, 887, 904, 911`
- **预算 400**（新增 20 条）：`543, 741, 744-745, 747-749, 755-756, 762, 764-765, 874-876, 881-882, 890, 927-928`
- **预算 800**（新增 20 条）：`513-518, 537-538, 742, 869, 889, 896-902, 921-922`
- **预算 1600**（新增 0 条）：`（无）`

（区间压缩表示；完整 `found_route_ids` 见 `sweep_budget*.json` 与本脚本的 `analysis_data.json`。）

## 4. 救回路线的 pair / family 分布

### 4.1 按 pair

| pair | 预算 200 | 预算 400 | 预算 800 | 预算 1600 |
|---|---|---|---|---|
| EN | 6 (+6) | 7 (+1) | 15 (+8) | 15 |
| ES | 9 (+9) | 20 (+11) | 21 (+1) | 21 |
| SW | 5 (+5) | 11 (+6) | 14 (+3) | 14 |
| NW | 2 (+2) | 4 (+2) | 12 (+8) | 12 |

括号内为该档相对上一档的边际新增。

### 4.2 按 family

| family | 预算 200 | 预算 400 | 预算 800 | 预算 1600 |
|---|---|---|---|---|
| L | - | - | - | - |
| TURN_S | 6 (+6) | 21 (+15) | 35 (+14) | 35 |
| SHIFT_TURN | 16 (+16) | 21 (+5) | 27 (+6) | 27 |
| Z3 | - | - | - | - |
| LEFT | - | - | - | - |
| Z5 | - | - | - | - |
| DOWN_LOOP | - | - | - | - |

### 4.3 family × pair 交叉（最大预算档）

| family | EN | ES | SW | NW | 合计 |
|---|---|---|---|---|---|
| SHIFT_TURN | 9 | 7 | 6 | 5 | 27 |
| TURN_S | 6 | 14 | 8 | 7 | 35 |

- **主要受益 family**：TURN_S（35 条）、SHIFT_TURN（27 条）。
- **主要受益 pair**：ES（21 条）、EN（15 条）、SW（14 条）、NW（12 条）。

## 5. 未救回路线的失败分析

三分类定义（互斥，逐路线判定，来源为 sweep JSON 的 `reason` 与 `rejection_counts`）：

- `candidate budget exhausted`：`rejection_counts` 中出现 `candidate_budget_exhausted`，即已评估满该档预算仍有候选未评估完；
- `current layout blocks all candidates`：队列被完整枚举（evaluated 小于预算）但全部被严格索引判非法，`reason=no_legal_candidate`；
- `no candidate generated`：扩展候选库在该布局下没有产生任何候选，`evaluated=0`、`reason=no_candidate_generated`。

| 预算 | 未救回 | 预算耗尽 | 当前布局阻挡 | 无候选生成 |
|---|---|---|---|---|
| 200 | 284 | 146 | 96 | 42 |
| 400 | 264 | 85 | 137 | 42 |
| 800 | 244 | 23 | 179 | 42 |
| 1600 | 244 | 3 | 199 | 42 |

### 5.1 几何拒绝原因聚合（未救回路线，剔除预算标记）

| 拒绝原因 | 预算 200 | 预算 400 | 预算 800 | 预算 1600 |
|---|---|---|---|---|
| double_cross | 21188 | 31481 | 39479 | 47298 |
| spacing | 9240 | 15427 | 18052 | 18923 |
| tangent_touch | 3069 | 3843 | 3966 | 4306 |

注：绝对计数随预算提高而增加是必然的（所有路线都评估了更多候选），有意义的是同一预算下各原因的相对占比。预算 1600 档占比：double_cross 67.1%、spacing 26.8%、tangent_touch 6.1%——几何拒绝的主因始终是 `double_cross`（候选与已布通波导发生两处交叉）。

### 5.2 blocker 频次 Top-15（最大预算档）

下表为预算 1600 档的 blocker 频次 Top-15（blocker = 拒绝某个候选的已布通路线；「影响路线数」= 有多少条未救回路线被该 blocker 拒绝过）。

| # | blocker route_id | 出现次数 | 影响路线数 | 占全部 blocker 次数 | blocker 所属 pair |
|---|---|---|---|---|---|
| 1 | 750 | 6891 | 99 | 9.77% | ES |
| 2 | 885 | 4128 | 79 | 5.85% | SW |
| 3 | 679 | 2248 | 64 | 3.19% | ES |
| 4 | 760 | 2171 | 69 | 3.08% | ES |
| 5 | 929 | 1656 | 92 | 2.35% | NW |
| 6 | 893 | 1305 | 85 | 1.85% | SW |
| 7 | 746 | 1280 | 83 | 1.81% | ES |
| 8 | 884 | 1208 | 66 | 1.71% | SW |
| 9 | 677 | 1156 | 48 | 1.64% | ES |
| 10 | 888 | 1125 | 60 | 1.60% | SW |
| 11 | 675 | 1036 | 39 | 1.47% | ES |
| 12 | 768 | 1030 | 66 | 1.46% | ES |
| 13 | 801 | 1025 | 38 | 1.45% | SW |
| 14 | 581 | 977 | 41 | 1.39% | EN |
| 15 | 549 | 964 | 74 | 1.37% | EN |

预算 1600 档 blocker 总次数 70,527，涉及 206 条已布通路线；Top-15 占比 40.0%。

### 5.3 blocker 频次 Top-15（预算 200，对照）

| # | blocker route_id | 出现次数 | 影响路线数 | 占全部 blocker 次数 | blocker 所属 pair |
|---|---|---|---|---|---|
| 1 | 750 | 1813 | 98 | 5.41% | ES |
| 2 | 746 | 1365 | 81 | 4.07% | ES |
| 3 | 885 | 1148 | 77 | 3.43% | SW |
| 4 | 929 | 837 | 66 | 2.50% | NW |
| 5 | 549 | 791 | 47 | 2.36% | EN |
| 6 | 893 | 771 | 74 | 2.30% | SW |
| 7 | 679 | 641 | 74 | 1.91% | ES |
| 8 | 760 | 632 | 53 | 1.89% | ES |
| 9 | 801 | 602 | 30 | 1.80% | SW |
| 10 | 547 | 588 | 53 | 1.76% | EN |
| 11 | 768 | 558 | 49 | 1.67% | ES |
| 12 | 674 | 518 | 23 | 1.55% | ES |
| 13 | 678 | 502 | 46 | 1.50% | ES |
| 14 | 680 | 497 | 43 | 1.48% | ES |
| 15 | 675 | 492 | 42 | 1.47% | ES |

该档 blocker 总次数 33,497，涉及 206 条已布通路线。

预算 400、800 档的 blocker Top-15 未重复列出，见 `analysis_data.json` 中 `failures[*].blockers.top`（四档齐全）。

**解释**：随着预算提高，`预算耗尽` 类路线逐步转为`当前布局阻挡` 类（队列被完整枚举），而 `无候选生成` 类的数量不随预算变化——后者的瓶颈不在评估预算，而在候选库/布局。

## 6. 128 条历史 `no_candidate_generated` corner 路线的候选覆盖

口径说明：

- **empty-layout**：不放置任何历史已布通路线，仅保留 CSV 端口固定出入线（所有候选生成器共享的静态“必然占用线”）以及 `D56Index` 的空索引。该口径衡量“当前 D56 扩展候选库能否为这条路线几何生成合法候选”；
- **base-layout**：冻结的 206 条已布通路线全部装入精确索引，衡量“生成出来的候选中有多少能真正插入当前布局”；
- 两种口径都枚举 **完整候选队列**（与 200/400/800/1600 预算无关），每路线每口径一次；本次覆盖计算耗时 437.6s（6 进程）。

### 6.1 总体覆盖

| 指标 | empty-layout | base-layout |
|---|---|---|
| 路线数 | 128 | 128 |
| 生成候选总数（generated） | 2,903 | 2,728 |
| 其中通过严格 D56 索引的合法候选 | 2,903 | 0 |
| 合法候选均值/路线 | 22.7 | 0.0 |
| 合法候选最大值/路线 | 90 | 0 |
| 0 合法候选路线数 | 42 | 128 |
| 其中“连候选都生成不出来”的路线数 | 42 | 42 |
| 首个合法候选位置中位数 | 0 | - |

empty-layout 使用空索引，生成的候选没有已布通路线可冲突，因此“生成数”与“合法数”相等；base-layout 的差异即为冻结布局造成的拒绝。

### 6.2 每路线合法候选数分布

| 合法候选数区间 | empty-layout 路线数 | base-layout 路线数 |
|---|---|---|
| 0 | 42 | 128 |
| 1-9 | 19 | 0 |
| 10-99 | 67 | 0 |
| 100-999 | 0 | 0 |
| >=1000 | 0 | 0 |

### 6.3 empty-layout 下候选族贡献

| family | empty-layout 合法候选数 | 覆盖路线数 |
|---|---|---|
| L | 0 | 0 |
| TURN_S | 0 | 0 |
| SHIFT_TURN | 0 | 0 |
| Z3 | 0 | 0 |
| LEFT | 0 | 0 |
| Z5 | 516 | 58 |
| DOWN_LOOP | 2,387 | 86 |

### 6.4 覆盖交叉分类

| 类别 | 路线数 |
|---|---|
| empty-layout ≥1 且 base-layout ≥1（可生成且可插入当前布局） | 0 |
| empty-layout ≥1 且 base-layout = 0（可生成但当前布局全部阻挡） | 86 |
| empty-layout = 0 且 base-layout ≥1（逻辑上不应出现） | 0 |
| empty-layout = 0 且 base-layout = 0（当前扩展候选库未找到候选） | 42 |

### 6.5 仍然 0 候选的路线 ID

**empty-layout 下 0 合法候选（42 条）**，即“当前 D56 扩展候选库未找到候选”的路线：

```
618, 625-628, 633-636, 638, 641-644, 649-652, 657-658, 769-774, 777-780, 785-786, 1009-1012, 1017-1022
```

**base-layout 下 0 条可插入候选（128 条）**：

```
609-672, 769-800, 993-1024
```

集合一致性校验：empty-layout 的 0 生成集合、base-layout 的 0 生成集合、以及 sweep 每一档 `no_candidate_generated` 的路线集合三者完全一致：**True**（每档均为 42 条）。

### 6.6 与预算 sweep 的交叉校验

| 预算档 | 这 128 条中 sweep 实际救回数 | 按 base-layout 首个可插入候选位置预测的救回数 |
|---|---|---|
| 200 | 0 | 0 |
| 400 | 0 | 0 |
| 800 | 0 | 0 |
| 1600 | 0 | 0 |

逐路线预测“预算 b 下是否救回” ⇔ “base-layout 首个可插入候选的位置 < b”，与 sweep 实测对比：不一致 **0** 条（完全一致）。

### 6.7 结论（严格表述）

- 128 条历史 `no_candidate_generated` corner 路线中，扩展候选库在 empty-layout 口径下能为 **86** 条生成合法几何候选（共 2,903 条，均值 22.7 条/路线）；仍有 **42** 条在当前 D56 扩展候选库下未找到候选。
- 这 42 条在三处完全一致（empty-layout 0 生成 / base-layout 0 生成 / sweep 各档 `no_candidate_generated`），说明它们的 0 候选与评估预算、与已布通路线都无关，是当前 D56 扩展候选库（在当前端口固定出入线约束下）的覆盖缺口。
- 在冻结 BASE 布局上，这 128 条中只有 **0** 条存在至少 1 条可插入候选，其余 **128** 条在冻结布局下全部候选均被严格索引判非法：其中 86 条是“能生成、但当前布局全部阻挡”（属于布局占位/顺序问题，是 R&R 实验的范畴），另外 42 条连候选都生成不出来。
- 候选族贡献：empty-layout 下全部 2,903 条合法候选只来自 Z5（516 条 / 58 条路线）、DOWN_LOOP（2,387 条 / 86 条路线），L / TURN_S / SHIFT_TURN / Z3 / LEFT 五个族贡献为 0——说明这批 corner 几何只有扩展的 loop 族能覆盖，但覆盖后仍被当前布局阻挡。
- 上述“0 候选”只应表述为“当前 D56 扩展候选库在当前（空/冻结）布局下未找到候选”，**不能**推断该连接在物理上绝对不可布通：候选库仍是有限族（L/TURN_S/SHIFT_TURN/Z3/LEFT/Z5/DOWN_LOOP），且 empty-layout 仍施加全部端口固定出入线约束（保守口径），不排除存在库外 D56 合法几何。

## 7. 结论摘要与产物

### 7.1 结论摘要

1. 四档预算救回路线数：200 → 22 条；400 → 42 条；800 → 62 条；1600 → 62 条（累计上限 62/306）。
2. 边际收益：200→400 新增 20 条；400→800 新增 20 条；800→1600 新增 0 条（累计 22 → 62）。
3. 128 条历史无候选 corner 路线：扩展候选库 empty-layout 下 86/128 可生成合法候选（2,903 条，仅来自 Z5、DOWN_LOOP），仍 42 条未找到候选；冻结 BASE 布局下 0/128 可插入 → 对能生成候选的路线，瓶颈是已有布局占位而非候选预算（86 条可生成但全部被阻挡），另 42 条属于候选库覆盖缺口。
4. 预算建议：候选评估预算取 800 已饱和（800→1600 新增 0 条）；若以评估成本优先，400 档即可拿到 67.7% 的最终收益。

### 7.2 产物清单

| 文件 | 内容 |
|---|---|
| `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\outputs\four_side_1024_v2_candidate_rr_v01\candidates_budget\sweep_budget200.json` … `sweep_budget1600.json` | 每档预算的 summary + 306 条逐路线明细 |
| `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\outputs\four_side_1024_v2_candidate_rr_v01\candidates_budget\sweep_summary.json` | 四档 summary 列表 |
| `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\outputs\four_side_1024_v2_candidate_rr_v01\candidates_budget\coverage_128_corner_routes.json` | 128 条 corner 路线全队列覆盖明细（两种口径） |
| `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\outputs\four_side_1024_v2_candidate_rr_v01\candidates_budget\analysis_data.json` | 本报告全部数字的机器可读版本 |
| `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\outputs\four_side_1024_v2_candidate_rr_v01\candidates_budget\figures\fig1_budget_vs_cumulative_found.png` … `fig5_corner_coverage.png` | 5 张图 |
| `C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D\outputs\four_side_1024_v2_candidate_rr_v01\candidates_budget\figures\figure_data.json` | 每张图的数据序列 |

报告生成耗时 1.3s。
