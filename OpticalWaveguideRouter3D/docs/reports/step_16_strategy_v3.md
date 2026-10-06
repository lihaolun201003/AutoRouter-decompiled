# Step 16 — 三维布线策略 v3：静态生成失败缓存与候选窗口几何余量（512 对照实验）

日期：2026-10-05。本轮只实现两项默认关闭的新功能，并在现有 512 合成输入上做四组对照实验。
真实 1024 端口数据尚未提供，本轮不生成、不冒充真实端口数据，不启动 1024 全量实验。
所有指标仍是 **0.1 mm 中心线近距对**，不代表完整损耗、串扰或制造合规。

本轮功能对照的 A/B/C/D 是**新功能消融**，与历史策略 A/B/C 无关；目录名均带有区分后缀。

## 一、修改文件与实现说明

### 1.1 修改文件

| 文件 | 修改 |
| --- | --- |
| `src/layer_assignment_3d.py` | `elevation_candidates` 新增 keyword 参数 `window_slack_mm=0.0`；pad 由 `max(1e-7,clearance)/length` 改为 `(max(1e-7,clearance)+window_slack_mm)/length`，并校验余量为有限非负值 |
| `src/three_layer_assignment_3d.py` | `candidate_families` 透传 `window_slack_mm`（默认 0.0） |
| `src/strategy_v2_3d.py` | 新增 `generation_input_key`、`generation_cache_hit`；`run_strategy_v2` 新增 `generation_failure_cache=False`、`window_slack_mm=0.0` 两个 keyword 参数及 C 策略的调度跳过；ledger 与结果新增缓存/跳过记账字段；模块 docstring 补充说明 |
| `tests/test_strategy_v3_features.py` | 新增 10 个回归测试 |
| `scripts/verify_window_slack_v3.py` | 新增：331 个已记录自检歧义候选的余量探针 |
| `scripts/run_3d_strategy_v3.py` | 新增：四组消融实验驱动 |
| `scripts/summarize_3d_strategy_v3.py` | 新增：跨组汇总分析 |

历史入口（`scripts/run_3d_strategy_v2_rev2.py`、`scripts/run_3d_strategy_v2.py`、`src/sequential_elevation_3d.py` 等）未改动，默认行为逐字节不变（由测试与 A 组实验共同验证）。

### 1.2 静态生成失败缓存

- 缓存键 `generation_input_key(plan_route, points, config, window_slack_mm)` 覆盖：实际使用的**冻结平面几何**（逐 primitive 结构指纹）、**实际目标锚点**（saved crossing 锚点或当前几何分析的动态锚点）、**全部配置层平面**、以及全部生成配置（clearance、required radius、transition policy、parameter status、window slack）。不以目标路线 ID 为键。
- 调度跳过条件：**仅当两个当前可移动 victim 都在完全相同的生成输入下记录为零候选**时，才把该目标从本轮待尝试集合中移除，记一条跳过事件，**不产生 step、不消耗 50 次目标尝试上限、不消耗候选评价预算**。
- 动态锚点在每次跳过验证时从**当前布局**重新解析（saved 锚点优先；否则重跑当前碰撞分析），锚点变化即键变化、目标重新可尝试。
- 动态验收失败走**全局布局版本缓存**：缓存记录的是目标失败当时的 `layout_version`，任何被接受的路线修改都会递增该版本、使旧失败失效（第三方路线变化后失败目标可重新评估）；旧的按目标"两条路线版本"缓存未恢复。
- 一方零候选时另一方仍正常生成与评价；非零候选记录（有候选但被拒）永远不算结构性失败。
- 开关：`run_strategy_v2(..., generation_failure_cache=True)`，仅对 strategy='C' 生效；默认关闭。

### 1.3 候选窗口几何余量

- `pad = (max(1e-7, clearance_mm) + window_slack_mm) / length`。记 **δ = window_slack_mm / 该 primitive 的直线长度**：pad 由 `clearance/length` 增到 `(clearance + slack)/length`，于是可用区间 `[lo, hi]` 的两端各内缩 δ（`lo+δ`、`hi−δ`），窗口宽度因此缩小 **2δ**；窗口起点随位置参数 f 的位移为 **(1−2f)·δ**（f=0 起点锚定处平移到 +δ、f=0.5 中间位置不动、f=1 贴右边界处平移到 −δ）。过渡长度取 `run/length`，不随 pad 改变、保持不变；但窗口宽度只剩 `(hi−lo)−2δ`，收缩后 `hi−lo < run/length` 的 primitive 不再产生任何窗口——勉强可行的窗口可能因此从枚举中消失。
- **slack = 1e-5 mm（10 nm）**。依据：候选自检的 ADAPTIVE_CHORD_BOUNDS 收敛界最坏为 `distance_tol=1e-6 mm`，解析分类容差为 `1e-9 mm`；1e-5 mm 是最坏界宽的 10 倍、解析容差的 1e4 倍，对约 5 mm 的窗口只相当于其长度的 2e-6、对 300 mm 板面为 3e-8。是否改变判定不作先验断言，只给本次探针的实测：重建的 331 条已记录歧义候选中 331/331 由 AMBIGUOUS_CLEARANCE 变为 CLEAR，对应 31 个任务的候选总数 666→666 不变（见 1.4 节）；该实测只覆盖这 331 条记录。
- 判据不变：clearance 仍为 0.1 mm（没有为消除歧义而放宽阈值）；最小曲率半径、端点、二维投影、保守间距判定与完整验收规则全部保持、未随本轮改动调整。本节只陈述上面的实测结果（331/331 变 CLEAR、候选总数 666→666 不变），不把它推广成对未测输入或其他候选的保证。
- 配置：`run_strategy_v2(..., window_slack_mm=1e-5)`；默认 0.0 保持历史行为。

### 1.4 331 个已记录自检歧义的复核（真实数据）

`scripts/verify_window_slack_v3.py` 从冻结平面几何与 saved CROSS 锚点重建修正版 C 保存的全部 331 条 `SELF_AMBIGUOUS_CLEARANCE` 候选行（31 个生成任务），对每条按新枚举的就近窗口（2δ 内匹配，体现 f 相关的移动方向）重建对应候选：

- **331 / 331 全部由 AMBIGUOUS_CLEARANCE 变为 CLEAR**（0 条仍歧义、0 条伪碰撞、0 条无法匹配窗口）。
- 31 个任务的可用候选总数 **666 → 666 不变**；31 个任务的层失败原因无变化。
- 样本（step 2、target (9,34)、route 34、layer 1、candidate 0/1/2）：最小距离由约 0.09999999999 变为 0.10000999999（= 0.1 + 1e-5 减浮点残差），与设计一致。

## 二、测试结果及跳过范围

- 3D `.venv`（Python 3.10.11）全量：**732 passed, 4 skipped**（`outputs/3d_strategy_v3/pytest_full_v3.log`）。
- 4 个跳过是 **4 个测试模块**（模块级 `pytest.importorskip("scipy")`）：`tests/test_opt2d.py`、`tests/test_opt2d_step13.py`、`tests/test_opt2d_step13_fixes.py`、`tests/test_opt2d_step14.py`；不是"只跳过 4 个用例"。
- 使用 2D 项目解释器（`OpticalWaveguideRouter2D/.venv`，scipy 1.15.3）运行这四个模块：**61 passed in 365.31s**（`outputs/3d_strategy_v3/pytest_opt2d_2d_env.log`）。
- 新增 10 个 v3 功能测试覆盖：结构性零候选不反复占用目标尝试（50→27 步、重复 25→0）；第三方变化后动态失败仍重新评价（stacking 场景轨迹不变）；锚点/几何/层/配置（含 slack）变化使缓存失效；一方失败不屏蔽另一方；默认关闭保持原行为（含生成输出逐位一致）；边界候选加余量后 CLEAR 且端点、XY、C0/C1、曲率全部保持；真实碰撞在余量下仍被拒；余量可移除贴边窗口（1.5e-5 mm 裕度场景）；拒绝与跳过不修改路线；512 真实样本复现并转 CLEAR。

## 三、512 四组对照实验

同一输入（`LEGACY_512_SMOOTHED_P0`）、同一初态（冻结二维 z=0 路线）、同一几何阈值、候选评价预算 720、目标尝试上限 50、策略 C。

| 组 | 生成缓存 | 窗口余量 | 终态近距对 | 未决对 | 接受 | 重定位 | 额外长度 mm | 过渡数 | 目标尝试 | 不同目标 | 重复尝试 | 跳过事件 | 生成候选 | 实际评价 | 完整邻居验收 | 自检歧义 | 零候选 victim 次 | 预算使用 | 停止原因 | 运行 s |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| A 基线原行为 | 关 | 0 | **44,274** | 3 | 22 | 0 | 8.405220 | 44 | 50 | 25 | 25 | 0 | 666 | 666 | 335 | 331 | 69 | 92.5% | TARGET_LIMIT | 199.7 |
| B 仅生成缓存 | 开 | 0 | **43,750** | 3 | 24 | 0 | 8.893004 | 48 | 27 | 27 | **0** | 28 | 765 | 720 | 364 | 356 | 19 | 100% | CANDIDATE_BUDGET_EXHAUSTED | 209.8 |
| C 仅窗口余量 | 关 | 1e-5 | **43,161** | 3 | 23 | 0 | 6.912199 | 46 | 50 | 26 | 24 | 0 | 711 | 711 | 711 | **0** | 67 | 98.8% | TARGET_LIMIT | 374.7 |
| D 两项同开 | 开 | 1e-5 | **42,909** | 3 | 24 | 0 | 7.156091 | 48 | 27 | 27 | **0** | 26 | 765 | 720 | 720 | **0** | 19 | 100% | CANDIDATE_BUDGET_EXHAUSTED | 373.4 |

相对初态 49,518 对：A 减 5,244（10.59%）、B 减 5,768（11.65%）、C 减 6,357（12.84%）、D 减 6,609（13.35%）。

关键观察（如实记录）：

1. **A 组完整复现修正版 C 的基线与终端**：终态 44,274、接受 22、评价 666、TARGET_LIMIT，且 `decisions.json` 的 SHA256 与修正版 C **逐字节相同**（`c322e4b1…`），终态路线、近距集合、预算曲线、台账共同字段全部一致。运行内比较器中显示的 "DIFFERS" 仅为内存元组与落盘列表的表示差异，严格落盘核对见 `A_baseline_original/previous_revision_strict_check.json`（verdict EXACT_MATCH），该严格结果已并入 `summary_all.json`（`previous_revision_comparison.verdict = EXACT_MATCH_ON_DISK`，同时保留原始 in-run 字段）。
2. **B 组消除重复调度**：目标尝试 50→27、重复 25→0；跳过事件 28 次，且**只涉及两个独立目标 (290,433) 与 (290,291)**（A 组正是这两个目标分别重复尝试 14 次与 13 次），零候选 victim 尝试 69→19，NO_ACCEPTABLE_MOVE 步 28→3。需要说清的是：零候选本身不生成候选，也就不消耗候选评价预算；缓存的直接作用是**避免这两个失败目标反复占用 50 次正式目标尝试上限**，而不是节省候选调用——B 组的候选评价数反而因此增加（666→720），并在 720/720 预算耗尽时停止，实测耗时 209.8 s **高于** A 组的 199.7 s，不能写成"运行更快"。D 组同样是这两个目标、26 次跳过事件。
3. **B 组轨迹与历史策略 B 完全一致**：27 步序列、moved 路线、终态逐路线、ledger 数值（43,750 / 24 / 720 / 额外长度 8.893004）全部相同。机制解释：512 上无重定位接受、无"双方已抬升"目标，C 与 B 的差别只剩那两个零候选目标的重复尝试；生成缓存去掉重复后，C 的轨迹自然与 B 重合。这是机制结果，不是为复现 43,750 调参。
4. **C 组消除全部自检歧义**：331→0；每一条被评价的候选都通过基本评估（711/711），完整邻居验收 335→711，接受 23 次，终态 43,161、额外长度 6.912（比 A 更短）。
5. **D 组终态最低**：42,909（比 A 少 1,365 对），24 次接受，额外长度 7.156。
6. **耗时**：C/D 组单次运行约 374 s，高于 A/B 的约 200 s，原因是完整邻居验收次数翻倍（335→711/720），每条都要与 511 条其他路线分类。单次实测，不作为普遍效率结论。
7. **余量减少窗口的如实记录**：(34,177) 的 victim 177 的生成失败原因由 `INSUFFICIENT_TRANSITION_SPACE` 变为 `NO_VALID_TRANSITION_WINDOW`（窗口空间被 pad 增量推到零）；A 与 C 的共同 50 个生成任务中没有任何任务因余量失去或获得候选。探针的 31 个已记录任务窗口数不变。
8. 四组未决对均为 3（`TOUCHING_THRESHOLD`），与既有记录一致，未放宽阈值消除。

## 四、全量复核结果

每组终态执行 **130,816 对**全量复核，并核对保存重载：

| 组 | 复核对 | 近距集合与增量一致 | 未决集合一致 | 端点不变量 | C0/C1 | 过渡半径 | XY 投影 | 结论 |
| --- | ---: | --- | --- | --- | --- | --- | --- | --- |
| A | 130,816 | 是 | 是 | 是 | 是 | 是 | 是 | PASS（24.9 s） |
| B | 130,816 | 是 | 是 | 是 | 是 | 是 | 是 | PASS（28.4 s） |
| C | 130,816 | 是 | 是 | 是 | 是 | 是 | 是 | PASS（24.2 s） |
| D | 130,816 | 是 | 是 | 是 | 是 | 是 | 是 | PASS（25.8 s） |

## 五、结论口径纠正

- 修正版 512：C（重定位版）= **44,274**，B = **43,750**，两者不并列，历史上也从未"最优为 B"。
- 512 上 B 的额外长度（8.893004 mm）**高于** A（8.839448 mm）；只有 1024 上 B 的额外长度（71.916944 mm）低于 A（87.406597 mm）。引用时须区分规模。
- 本轮全部数字为中心线近距对指标；完整损耗、串扰与制造合规仍需平台约束与标定数据。
- 本轮 D 组 42,909 低于是因为搜索覆盖与候选质量变化（更多候选可用、重复尝试消除），不是放宽任何判据；四组的几何阈值、验收规则与复核流程完全一致。

## 六、产物与复现

绝对路径（Windows）：

- 实验根目录：`C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D\outputs\3d_strategy_v3\512_ablation\`
  - 各组子目录：`A_baseline_original\`、`B_generation_cache_only\`、`C_window_slack_only\`、`D_both_enabled\`（各含 `config.json`、`code_version.json`、`environment.json`、`decisions.json`、`generation_skips.json`、`curve.json`、`final_routes.json`、`collision_sets.json`、`ledger.json`、`recheck.json`、`summary.json`）
  - 跨组分析：`cross_group_analysis.json`、`comparison_groups.csv`、`run_v3_512.log`
  - A 组严格核对：`A_baseline_original\previous_revision_strict_check.json`
- 余量探针：`outputs\3d_strategy_v3\window_slack_probe\window_slack_probe.json`
- 测试日志：`outputs\3d_strategy_v3\pytest_full_v3.log`（3D 732 passed/4 模块跳过）、`outputs\3d_strategy_v3\pytest_opt2d_2d_env.log`（2D 环境 61 passed）

复现命令（项目根运行）：

```text
.venv\Scripts\python.exe -B scripts\run_3d_strategy_v3.py . outputs\3d_strategy_v3\512_ablation
.venv\Scripts\python.exe -B scripts\summarize_3d_strategy_v3.py . outputs\3d_strategy_v3\512_ablation
.venv\Scripts\python.exe -B scripts\verify_window_slack_v3.py . outputs\3d_strategy_v3\window_slack_probe
.venv\Scripts\python.exe -B -m pytest tests\ -q
..\OpticalWaveguideRouter2D\.venv\Scripts\python.exe -B -m pytest tests\test_opt2d.py tests\test_opt2d_step13.py tests\test_opt2d_step13_fixes.py tests\test_opt2d_step14.py -q
```

## 七、已证实改善、负结果与仍未验证的问题

**已证实改善（512，同预算）**

- 生成缓存：结构性零候选目标不再反复占用目标尝试（50→27 步、重复 25→0），且动态失败语义保持不变（stacking 回归 + A/B 轨迹解释）；它不减少候选评价次数，也不缩短运行时间（B 组 720/720 预算耗尽、209.8 s 高于 A 组 199.7 s）。
- 窗口余量：512 上全部 331 条已记录自检歧义变 CLEAR，可用候选（每评价候选的基本评估通过率）由约 50% 提高到 100%，终态 44,274→43,161（去余量单独作用）；两项同开 42,909。

**负结果与代价**

- 余量使 (34,177) victim 177 的失败原因从 INSUFFICIENT 变为 NO_VALID_WINDOW（窗口空间更紧）；未发现某个任务因此从"可生成"变为"零候选"，但该类边界任务在别的输入上可能失去窗口。
- C/D 组单次运行时间约 374 s，高于 A/B 的约 200 s；原因是完整邻居验收次数翻倍。效率结论需要独立重复与曲线（本轮不做）。
- B 组（与 D 组）在 720 预算耗尽时停止，未到目标上限；终态受预算口径影响，不能声称收敛。
- 重定位在本轮四组主实验中依旧 0 次接受（四组都没有触发重定位）。**这一条已被下面的补充实验部分推翻**：
  把同一窗口余量加到 Step 15 的固定重定位诊断上、其余条件全部不变后，E 组第一次接受了重定位。见第八节。

**仍未验证的问题**

- 1024 及其他输入上的行为未测：余量是否会让某些（更紧的）窗口消失、缓存能否同样消除 (18,19) 的 133 次重复，均无证据。
- 本轮只记录单次运行的耗时；未做重复测量、未做候选验收性能剖析。
- D 组 42,909 的改进未做目标级归因（哪些目标因哪项功能改变），也未做不同起点的稳健性检查。
- 真实端口数据到达后，仍需先做输入审计，再作为独立外部验证，不能按终态反复调参。
- 补充实验（第八节）只覆盖一个起点、一份 20 目标清单与一个余量取值；旧诊断 70 条重定位歧义候选中只有 10 条在本轮有唯一对应候选，
  其余 60 条所在的生成任务本轮因目标已不再近距而没有执行，既不能算已解决也不能算未解决。

## 八、补充实验：把同一余量加到 Step 15 固定重定位诊断上（新 D / 新 E）

在同一诊断（起点为 512 条 B 终态 43,750 对近距、24 条已抬升路线；预声明 20 个目标，双方均已抬升 10 对、
仅一方已抬升 10 对；同一顺序、同一几何与验收规则、候选评价上限 720 次）上只增加 `window_slack_mm=1e-5`，
静态生成失败缓存保持关闭。目标清单按原规则重新推导并与 Step 15 的 `target_list.json` 逐项比对为完全相同。

| 组 | 终态近距对 | 接受修改 | 接受重定位 | 重定位路线尝试 | 重定位候选评价 | 候选评价合计 | 相对平面额外长度 mm | 单次运行 s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 旧诊断 D（余量 0） | 42,112 | 8 | 0 | 0 | 0 | 324 | 13.0153 | 124.7 |
| 新诊断 D（余量 1e-5） | 42,112 | 8 | 0 | 0 | 0 | 324 | 13.0153 | 114.2 |
| 旧诊断 E（余量 0） | 42,112 | 8 | 0 | 28 | 126 | 450 | 13.0153 | 188.0 |
| 新诊断 E（余量 1e-5） | **42,083** | 9 | **1** | 16 | 18 | 342 | 13.4495 | 129.8 |

- 新 D 与旧 D 的决策序列、终态近距集合、未决集合和统计指标保持一致（42,112 对、8 次首次抬升、324 次评价、
  额外长度 13.0153 mm），但 8 条路线的窗口几何发生了约 1e-5 mm 的平移；不声称几何或原始 decisions 逐字节相同。
- 新 E 的第 4 步（目标 (34,273)）接受了重定位：路线 34 由层 1 改到层 2，移除 26 对近距、新增 0 对，
  全局近距对 43,750 → 43,724；随后 6 个原本待处理的"双方均已抬升"目标不再处于近距状态，
  因此重定位候选评价从 126 次降到 18 次、候选评价合计从 450 次降到 342 次，终态由 42,112 降到 42,083（少 29 对）。
  29 对差异的来源经逐步核对为 26 + 3：路线 34 的重定位直接移除 26 对；后续路线 0、1、13 的首次抬升各少新增 1 对（共 3 对）。
  重定位单步长度变化与最终 D/E 的终态额外长度差一致（0.434228 mm，两者在 1e-9 mm 内相同）。
  被接受候选正是旧诊断中因 `SELF_AMBIGUOUS_CLEARANCE` 而永远无法判定的 5 条层 2 候选之一（candidate_index 11），
  它不是放宽任何判据的结果：阈值、半径、端点、XY 投影、C0/C1、完整邻线验收与"全局近距对必须严格下降"全部照旧。
- 逐候选对应（不做"总数下降即全部解决"的推断）：旧诊断 E 的 70 条重定位自检歧义候选中，
  只有 10 条在本轮有唯一对应候选（5 条通过基本评价、5 条仍因 TARGET_NOT_CLEARED 被拒），
  其余 60 条所在的生成任务本轮没有执行，不计入任何通过率。全部运动类别合并为 208 条，对应 148 条（143 + 5）；
  这 143 条通过基本评价的候选中，139 条通过完整邻线验收、4 条被完整验收拒绝（NO_STRICT_GLOBAL_DECREASE）。
  通过验收不等于实际执行：一个步骤只执行它选中的那一个候选，两条诊断实际执行的修改合计 17 次
  （新 D 8 次、新 E 9 次，其中重定位 1 次）；重定位范围 10 条对应候选中 5 条通过基本评价，其中 1 条通过完整验收（即被接受的那一条）、4 条被完整验收拒绝。
- 本次接受只发生在一个起点、一份目标清单与一个余量取值上；D 组终态不变；运行时间仍为单次实测。

产物：`outputs\3d_strategy_v3\512_relocation_slack_diagnostic\`（含 `analysis.json`、`movement_stats.json`、
`length_ledger.json`、`candidate_correspondence.json`、`target_outcomes.csv`、`recheck_{D,E}.json`、`manifest.json`）；
图：`outputs\3d_strategy_v3\figures\f4_diagnostic_comparison.png`、`f5_relocation_rejections.png`、
`f7_route34_relocation_before_after.png`。旧诊断目录未被覆盖。

复现命令（项目根运行）：

```text
.venv\Scripts\python.exe -B scripts\run_3d_relocation_slack_diagnostic.py . outputs\3d_strategy_v3\512_relocation_slack_diagnostic
.venv\Scripts\python.exe -B scripts\analyze_relocation_slack_diagnostic.py . outputs\3d_strategy_v3\512_relocation_slack_diagnostic
.venv\Scripts\python.exe -B scripts\visualize_relocation_slack.py . outputs\3d_strategy_v3\figures
```
