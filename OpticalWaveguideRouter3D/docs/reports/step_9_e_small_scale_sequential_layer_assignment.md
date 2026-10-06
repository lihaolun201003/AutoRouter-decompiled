# Step 9-E — Small-Scale Automatic Sequential Elevation

## 1. Scope

**PASS。** 从保存的 512 条路线开始，自动连续处理 30 次当前 collision 目标，完成 12 次单路线抬层。仅运行这一小规模实验，不扩大到全量优化或 1024。正式二维 baseline 保持只读。

实现：`src/sequential_elevation_3d.py`。本阶段没有 transaction、version、stale candidate、protected pair 或复杂 rollback；失败候选不替换内存路线即可。

## 2. Initial 3D State

读取 `step_8_5_legacy_512_plot_geometry.json`，反序列化 512 条 SmoothedRoute2D 并全部解析 lift 至 Layer 0；未运行 allocator。保存的 physical CROSS 文件只提供窗口锚点，不代替当前三维 collision 判定。

初始检查 C(512,2)=130,816 对，当前 clearance 下有 **49,518 个 COLLISION pair**。这是中心线 clearance 违规路线对数，不是二维 physical CROSS 事件数，也不是 multi 数。另有 3 个未决/边界 pair，单列保存，不计为 COLLISION，也不称其 CLEAR。

## 3. Experimental Parameters

沿用显式配置：Layer 0 z=0 mm，Layer 1 z=1 mm；clearance=0.1 mm；required radius=5 mm；LINE_ONLY_FINITE_WINDOWS；EXPERIMENTAL_SYNTHETIC。过渡 run 由 9-B 公式计算，并沿用 9-D 数值余量，约 4.967294138 mm。均为实验值，不是正式制造参数。

## 4. Collision Target Ordering

每轮在当前 collision 集合中选 canonical route ID 字典序最小的 pair；已在本次实验失败或 BOTH_ALREADY_ELEVATED 的目标跳过，避免反复停留在同一失败目标。成功后重算移动路线关联的所有 pair，再重新选择目标。若已消除 pair 以后重新出现，它仍可作为当前目标被选中，没有历史保护策略。

不预先固定 30 个 pair。因而 `skipped_already_clear=0` 表示没有预排列表需要逐项跳过；前一步顺带清除的 pair 自动不再进入目标集合。例如第一步移动 0 后，其 collision degree 由 95 变为 0，下一目标直接成为 (1,24)，而非继续处理 (0,25)/(0,26)。30 次 target attempts 包括成功和跳过，不是追求 30 次成功。

## 5. Victim Selection

用当前 collision pair 集合计算 degree；优先尝试 degree 小者，并列按 route_id 小者。每条路线最多抬层一次，已抬层则尝试另一条；两条均已抬层记录 BOTH_ALREADY_ELEVATED。

这是 project-specific heuristic，不是最优定理。本次成功均来自第一优先 victim，没有“第一 victim 无改进、第二 victim 成功”的真实案例；测试另覆盖该 fallback 分支。

## 6. Candidate Generation

直接复用 9-D 的 `elevation_candidates` 与基本评估：只切 Line 窗口，原 XY 不变，圆弧仅整体改变 z，不切弧。两端仍在 Layer 0，以一升一降 cosine 连接 Layer 1 中段。

有保存 CROSS 时使用其点作为窗口锚点；clearance-only collision 没有 CROSS 时，使用 9-C 给出的移动路线上的最近点作为有限窗口锚点。每个目标都先用当前路线完整确认 COLLISION。

候选需端点、连续性、切向方向、真实最小 radius、self-clearance 和目标 CLEAR 检查通过。沿用 9-D 的自检未决拒绝规则，没有为增加成功率放宽它。累计生成 162 个候选：78 个因 SELF_AMBIGUOUS_CLEARANCE 被拒绝，其余 84 个全部完成当前 511 邻线评价。

## 7. Candidate Ranking

同一 victim 的全部基本合法候选均评价，只有 after_collision_count < before_collision_count 才可选。按以下元组取最小：after count、新增 collision 数、extra length、高层平面长度、rise/fall 窗口索引和参数。没有加权和。

允许新增碰撞，只要求净下降；新旧集合差分别记录。候选邻线若存在未决分类则不接受，不能把数值未决当成已消除的碰撞。本次 84 个完成邻线评价的候选均净下降且无未决邻线，选出其中 12 个实际应用。

## 8. Sequential Elevation Algorithm

仅维护当前 routes、elevated_route_ids、collision set 和失败跳过集合。对候选，在局部变量构造路线并评价；选定后直接替换一条 routes[id]，刷新该路线的包围盒及其关联 pair。其余路线 pair 不变。

candidate-vs-other 使用当前 `RouteView.route`，其中包含此前已抬层路线；没有回退到原 Layer 0 几何。保存的候选评价记录列出参与检查的当前 elevated 邻线 ID。共完成 84×511=42,924 次候选邻线检查，不是每候选重算 130,816 对。

距离分类复用 9-C primitive API；包围盒与固定 z 下界足够时直接判 CLEAR，发现任一 primitive pair COLLISION 后提前返回。这里只请求分类，不请求无用的完整 route minimum；未决分类继续沿用 9-C 优先级。没有复杂空间索引或缓存系统。

## 9. Results

30 次目标：**12 次成功，18 次 BOTH_ALREADY_ELEVATED，0 次 NO_IMPROVING_SINGLE_ELEVATION**。第一 victim 失败→第二 victim 成功 0 次；因已抬层跳过 victim 36 次，对应 18 个两者均已抬层的目标。

| attempt | target | moved | route collisions before→after | 净减少 | 全局 after |
|---:|---|---:|---:|---:|---:|
| 1 | 0/24 | 0 | 95→0 | 95 | 49,423 |
| 2 | 1/24 | 1 | 95→0 | 95 | 49,328 |
| 3 | 2/20 | 20 | 64→0 | 64 | 49,264 |
| 4 | 2/21 | 21 | 63→1 | 62 | 49,202 |
| 5 | 2/24 | 2 | 78→2 | 76 | 49,126 |
| 8 | 3/24 | 3 | 78→2 | 76 | 49,050 |
| 11 | 4/5 | 4 | 285→0 | 285 | 48,765 |
| 12 | 5/6 | 5 | 284→1 | 283 | 48,482 |
| 14 | 6/7 | 6 | 283→2 | 281 | 48,201 |
| 17 | 7/8 | 7 | 282→3 | 279 | 47,922 |
| 21 | 8/13 | 13 | 211→4 | 207 | 47,715 |
| 26 | 8/14 | 14 | 211→4 | 207 | 47,508 |

Step 9-D 是从 baseline 独立开始的三次实验；本次以上各行在上一次修改后的同一布局中连续执行。结果不可混用。

## 10. Collision Reduction

**49,518→47,508，净减少 2,010（4.0591%）**。累计消除旧碰撞 2,029 次、新增碰撞 19 次，两者之差为 2,010；这里是逐次集合差事件的累计，不声称全部为不同 pair。

单次最大净减少 285，平均每次成功净减少 167.5。每次接受后全局 count 严格下降；失败/跳过时保持不变。3 个未决/边界 pair 保持原样：(45,161)、(46,232)、(84,160)。

曲线数据见 `outputs/step_9_e_collision_history.json`；完整 30 行见 `step_9_e_sequential_elevation_steps.csv`；summary、target_attempts、collision_sets 保存统计、候选记录与初末集合。未绘制正式图。

## 11. Elevated Routes

共 12 条不同路线：**0, 1, 2, 3, 4, 5, 6, 7, 13, 14, 20, 21**。每条只抬层一次，各两个 cosine，总计 24 个 transition。总 extra length **2.926703009629 mm**，每条约 0.243891917469 mm。

`outputs/step_9_e_final_route_state.json` 保存全部 512 条当前路线及每条 LAYER_0 / SINGLE_ELEVATION_0_1_0 状态；各成功窗口、过渡端点、radius 与长度在 target_attempts 中。它是本阶段独立实验输出，没有覆盖正式二维输出。

## 12. Failure Cases

主要限制已经出现：两条路线都抬层后发生的碰撞无法再由本策略处理。例如 (3,20)、(3,21) 及部分已抬层路线 4/5/6/7 与 13/14 的碰撞成为跳过目标。原先已清除的 (2,20)、(2,21)、(4,5) 等也重新出现，并按当前排序被再次选择后跳过。允许新增 collision 的代价在记录中可见。

候选级拒绝为 78 次 SELF_AMBIGUOUS_CLEARANCE。目标级没有空间不足导致的整体失败，也没有第二 victim 救回的真实案例；相关分支由有限 synthetic 测试覆盖。未扩大搜索来消除剩余碰撞。

## 13. Runtime

本机主要实验约 **23.47 s**（精确耗时见 summary 的 runtime_seconds），包含初始全部 pair 分类及 30 个目标；历史与新增测试约 6 s。额外一致性审计单独计时，见 consistency_checks 的 seconds，不混入算法 runtime。

审计从最终保存状态重建全部 130,816 对，验证与局部更新集合一致；INITIAL/FINAL 对照使用完整 `analyze_route3d_clearance` API，结果与分类快捷路径一致（数量见 consistency_checks）；同一 30 目标确定性复跑的逐步记录、最终 512 条路线均一致。另外根据每步新旧集合差独立核对当前 canonical 最小目标，包含清除后再次出现的 pair。审计没有增加目标或继续优化。

## 14. Tests

**668/668 PASS：历史 656 项 + 新增 12 项。** 覆盖 degree/victim 顺序、strict decrease、候选排序、成功替换/全局更新、失败不改变路线、当前已抬层几何参与判断、9-C 分类一致性、确定性复跑、目标上限、只读 baseline、后续 elevated 邻线和 fallback。没有加入版本或事务安全测试。

复现命令（项目根目录）：

```text
.venv\Scripts\python.exe -B scripts\validate_sequential_elevation_3d.py . . <输出目录>
.venv\Scripts\python.exe -B scripts\audit_sequential_elevation_3d.py . . <同一输出目录>
```

第一条可追加 `--tests-only`。tests、consistency_checks、file_integrity JSON 为对应证据，阶段前文件哈希保持不变。未安装依赖。

## 15. Limitations

仅验证前 30 次动态目标尝试，未证明全量 512 或 1024 可布通。当前仍有 47,508 个 COLLISION pair；两层、每路线一次抬层很快出现限制。degree 启发式不保证最优，有限 Line 窗口不保证找到全部可行解。self-clearance 仍沿用 9-C 对相邻正常连接的豁免语义。

没有实体截面、制造公差或正式层参数结论；3 个未决 pair 单列保留。无多 route 联合搜索、depth-2、重复抬层、三层、Arc 切割、loss 优化、GUI/GDS。

## 16. Verdict

**Step 9-E：PASS。** 自动连续流程实际完成 30 次目标；12 次接受均严格降低全局 collision pair 数；后续使用最新几何；失败候选不替换路线；历史测试通过；正式二维 baseline 未修改。本报告及保存 JSON/CSV 构成本阶段 checkpoint。到此停止。

## 17. Recommended Next Step

建议下一 Step 在单独授权的较大固定目标预算下复用同一简单算法，评估 512 连续抬层的收益饱和与剩余 collision 分布，为固定 1024 数据接入确定下一项最必要的改动；不先引入事务框架或联合搜索。本次未自行扩大到全 512 或 1024。
