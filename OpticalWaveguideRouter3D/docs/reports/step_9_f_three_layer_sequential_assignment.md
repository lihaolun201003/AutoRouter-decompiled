# Step 9-F — Three-Layer Sequential Assignment

## 1. Scope

**PASS。** 从同一原始 512 路线布局分别完成两层对照、三层实验，各 50 次 target attempts。三层最终 collision pair 比两层少 1,224；Layer 2 实际用于 8 条路线。没有扩大目标预算或运行 1024。

新增 `src/three_layer_assignment_3d.py`；在既有 9-D 构造器增加显式 target_layer_id，在 9-E 原循环中接入候选族和统一排序。原两层配置接口与 9-E 默认 30 次入口继续保留，未修改二维 allocator。

## 2. Motivation from Step 9-E

9-E 的 30 次动态目标中有 18 次 BOTH_ALREADY_ELEVATED，两层只能把所有新抬路线放到 Layer 1。本阶段测试新增 Layer 2 能否分散路线、减少再次碰撞。每路线仍最多抬层一次，不将已抬 Layer 1 路线再次搬到 Layer 2。

## 3. Three-Layer Configuration

新模块的 LayerConfiguration 仅允许固定实验配置：两层为 (id,z)=(0,0),(1,1)；三层再加 (2,2)，单位 mm。检查重复 ID/z、非法层数、非固定配置和显式参数。旧模块的两层 LayerConfiguration 保持原限制，历史测试不放宽。

两组 clearance=0.1 mm、required radius=5 mm，policy=LINE_ONLY_FINITE_WINDOWS，状态均为 **EXPERIMENTAL_SYNTHETIC**。z=1/2 mm 不作为正式制造层间距。

## 4. Transition Run

使用既有 helper：`L_min=pi*sqrt(R_required*abs(delta_z)/2)`，不硬编码近似值。

| family | Δz mm | 理论最小 run mm | 实际构造 |
|---|---:|---:|---|
| 0→1→0 | 1 | 4.967294132898 | 乘现有 (1+1e-9) 余量 |
| 0→2→0 | 2 | 7.024814731041 | 同样余量 |

每条路线升降各一段，实际两段 R_min 均再次检查满足 5 mm。Layer 2 过渡水平长度更长，不能强行塞进不足窗口。

## 5. Candidate Generation

同一未抬 victim 分别调用原 Line-window 枚举器生成每个配置层的全部候选。保持端口、XY 投影、圆弧结构，仅改变中段 z 并插入两个 cosine。基本验收继续使用 9-D/9-C：连续、切向方向、radius、自检、目标由 COLLISION 变 CLEAR；未决候选不放行。

每个基本合法候选完整检查其余 511 条**当前**路线，包含此前 Layer 1 和 Layer 2 的路线；0→2 过渡穿过中间高度时同样参加真实三维求距。候选评价与窗口信息保存在各组 attempts JSON。

## 6. Layer Selection Rule

同一 victim 的 Layer 1、Layer 2 候选全部评估后，统一按：after_collision_count、新增 collision 数、extra length、高层平面长度、target_layer_id、稳定窗口顺序排序。只接受 after < before。

不能在 Layer 1 找到一个可改善候选后停止。排序前四项相同时优先低层；不是以低层偏好覆盖更好的 collision 结果。第一 victim 两族均无改善才尝试第二 victim。每次只替换选中的一条内存路线，沿用原 canonical target、degree victim、局部 pair 更新与失败跳过规则。

## 7. Two-Layer Control

从原始 geometry 重新 lift 全部 512 条路线到 Layer 0，预算 50，与三层使用同一代码、clearance、radius、排序和初始 collision 集合。唯一策略差别为可选目标层集合。

两层前 30 次记录除新增层标记/候选族记录格式外，与保存的 9-E 逐步记录一致，证明没有另改对照算法。此后按同一规则继续至第 50 次。

## 8. Three-Layer Experiment

同样从原 baseline 开始，没有接着 9-E 最终状态运行。50 次中 22 次成功，28 次 BOTH_ALREADY_ELEVATED，0 次 NO_IMPROVING_SINGLE_ELEVATION。同一已抬路线没有再抬，状态仅为 LAYER_0、SINGLE_ELEVATION_0_1_0、SINGLE_ELEVATION_0_2_0。

两层/三层目标序列会随布局变化而分岔；公平条件是相同初始状态、规则和尝试预算，不是人为强制相同 target 列表。

## 9. Collision Reduction Comparison

| 指标 | 两层对照 | 三层实验 |
|---|---:|---:|
| target attempts | 50 | 50 |
| 初始 collision pairs | 49,518 | 49,518 |
| 最终 collision pairs | 46,624 | 45,400 |
| 净减少 | 2,894 | 4,118 |
| 净减少比例 | 5.8443% | 8.3162% |
| 成功 elevation | 16 | 22 |
| BOTH_ALREADY_ELEVATED | 34 | 28 |
| NO_IMPROVING | 0 | 0 |
| 累计旧 collision 消除 | 2,929 | 4,156 |
| 累计新 collision 产生 | 35 | 38 |
| 平均单次净减少 | 180.875 | 187.1818 |
| 最大单次净减少 | 285 | 285 |

**三层额外减少 1,224 个 collision pair。** 每次接受后 count 均严格下降。新旧碰撞数为逐次集合差累计，不是独立二维 CROSS 事件数。初始和最终均另有 3 个未决/边界 pair，单列保存，不计入 COLLISION，也不假报 CLEAR。

## 10. Layer Usage

两层：Layer 0 未抬 496 条，Layer 1 抬升 16 条。

三层：Layer 0 未抬 490 条，Layer 1 抬升 14 条，Layer 2 抬升 8 条。Layer 2 路线 ID：**5,7,21,24,25,26,27,28**。各组完整 ID 集合见 `step_9_f_layer_usage.json`。

Layer 2 被选中的八次，在同一当前状态、同一 victim 下，其最佳 after count 都低于 Layer 1：

| target / moved | L1 最佳 after | L2 最佳 after |
|---|---:|---:|
| 2/21，21 | 1 | 0 |
| 5/6，5 | 1 | 0 |
| 7/8，7 | 2 | 1 |
| 8/24，24 | 14 | 3 |
| 8/25，25 | 14 | 4 |
| 8/26，26 | 14 | 5 |
| 8/27，27 | 14 | 6 |
| 8/28，28 | 6 | 2 |

**Layer 2 独有成功 target 为 0。** 定义是：所选 victim/当前状态下，Layer 1 无可接受的严格改善候选，而 Layer 2 有。本次八次 Layer 2 选择中 Layer 1 也能改善，因此证据支持“Layer 2 改善幅度更好”，不支持“这些目标只有 Layer 2 才能解决”。不推断未尝试的另一 victim 的最优能力。

## 11. BOTH_ALREADY_ELEVATED Analysis

34→28，减少 6 次（约17.65%），但仍占三层预算的56%。Layer 2 分散了新抬路线，使相同预算内成功数由16增至22；不能彻底消除每路线只抬一次的限制。没有实现再次升层来人为降低该计数。

## 12. Length Overhead

| 指标 | 两层 | 三层 |
|---|---:|---:|
| 总 extra length mm | 3.902270679505 | 8.839448336078 |
| transition 数 | 32 | 44 |
| Layer 1 extra length 合计 mm | 3.902270679505 | 3.414486844567 |
| Layer 2 extra length 合计 mm | 0 | 5.424961491510 |

Layer 1 每条额外约0.243891917469 mm；Layer 2 每条约0.678120186439 mm。总长度增加既来自较高层过渡更长，也来自三层组多接受6条路线，不能全部归因于层高。这里只统计几何长度，没有拟合光学 loss。

## 13. Runtime

本机主要实验：两层 **40.59 s**，三层 **81.25 s**，均包含初始 pair 集合建立和50次目标。三层需要评价两个候选族且实际接受更多路线，运行量增加。单次运行时间不是稳定性能基准。

验证脚本 `scripts/validate_three_layer_assignment_3d.py` 输出两组 summary/steps/attempts/final_route_state/collision_sets，以及 comparison、layer_usage 和 tests；文件均以 step_9_f 命名，不覆盖 9-E。原始数据哈希在 summary 内。

## 14. Tests

**684/684 PASS：历史668项 + 新增16项。** 覆盖固定三层配置、重复ID/z、4层拒绝、Layer 2 run和几何、端口与R_min、完整两族枚举、统一排序/低层平局/高层更优、L1/L2当前邻线双向判断、每路线一次、50预算上限、同baseline、旧两层行为、确定性复跑和只读。

`audit_three_layer_assignment_3d.py` 已核对两组每步 canonical target、当前degree、全部合法候选的511邻线评价、统一排序和严格下降；分别重新建立最终全部130,816 pair集合；两层261对、三层373对与完整9-C API分类一致。两组从相同起点复跑各50次，逐步记录及最终512条路线均完全一致。审计结果见 `step_9_f_consistency_checks.json`。

项目根目录复现：

```text
.venv\Scripts\python.exe -B scripts\validate_three_layer_assignment_3d.py . . <输出目录>
.venv\Scripts\python.exe -B scripts\audit_three_layer_assignment_3d.py . . <同一输出目录>
```

首条可追加 `--tests-only`。文件完整性证据明确列出两处3D模块修改和所有新增文件；历史测试、正式二维源码和输出不修改，不安装依赖。

## 15. Limitations

仍有45,400个 collision pair，不能声称完成全局安全布线。只对50次预算作对照，未证明收益在更大规模下持续，也未证明degree heuristic或候选选择全局最优。层高与clearance仍是实验参数。

Layer 2 更长的窗口可能减少其他路线的可行空间；本次没有“L1完全失败、L2独有成功”的真实案例。沿用9-C自检与数值未决规则。没有重复抬层、Layer1→Layer2搬移、四层、Arc切割、XY rerouting、事务/版本系统、实体模型、loss、GUI/GDS。

## 16. Verdict

**Step 9-F：PASS，值得保留第三层作为实验选项。** 相同50预算下减少更多collision、实际使用Layer 2，并减少BOTH_ALREADY_ELEVATED；代价是更多长度和约双倍本次运行时间。收益不是碰撞归零或制造可行性证明。本报告及JSON/CSV作为阶段checkpoint，停止在9-F。

## 17. Recommended Next Step

建议单独授权下一阶段扩大固定目标预算，评估三层收益饱和与剩余碰撞分布，再安排固定1024数据接入；继续复用简单算法，不先增加联合搜索或事务框架。本次没有自行进入全512或1024。
