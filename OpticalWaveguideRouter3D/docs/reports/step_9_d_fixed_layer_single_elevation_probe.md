# Step 9-D — Fixed Layer Configuration & Single Elevation Probe

## 1. Scope

**PASS：单路线抬层实验。** Synthetic fixture 成功，保存二维 CROSS 的三组真实 pair 均成功；各暂选候选还完成其余 511 条 baseline 路线的独立验证，未新增碰撞。每次实验只移动一条路线，三次实验不叠加、不写回正式 routing。既有二维 baseline 与 Step 9-A/B/C 冻结。

新增模块 `src/layer_assignment_3d.py`、测试 `tests/test_layer_assignment_3d.py`、复现脚本 `scripts/validate_layer_assignment_3d.py`。保存证据为 `outputs/step_9_d_*.json`：tests、synthetic、real_pairs、local_validation、probe_summary、file_integrity。本报告与上述证据共同构成阶段 checkpoint。

## 2. Fixed Layer Configuration

`LayerConfiguration` 必须显式提供两层、clearance_mm、required_radius_mm、transition_policy、parameter_status。验证层数恰好为二、ID 不重复、z 不重复、Layer 0 在 z=0、Layer 1 高于 Layer 0、数值有限且 clearance/radius 为正。布尔值不作为数值参数接受。配置复制输入 layers，使用前重新验证。

仅支持 `LINE_ONLY_FINITE_WINDOWS` 与 `EXPERIMENTAL_SYNTHETIC`。没有任意层数、连续 z 优化或通用 CAD 接口，也不从二维参数隐式读入三维参数。

## 3. Experimental Parameters

| 参数 | 本次显式实验值 |
|---|---|
| Layer 0 | id=0，z=0 mm |
| Layer 1 | id=1，z=1 mm |
| clearance | 0.1 mm，中心线间距 |
| required radius | 5 mm |
| policy | LINE_ONLY_FINITE_WINDOWS |
| status | EXPERIMENTAL_SYNTHETIC |

**1 mm 仅为 synthetic experimental layer spacing，不是最终正式层间距。** 0.1 mm 同样不是制造标准；5 mm 是本次调用显式给出的曲率约束，没有复用二维默认配置。

## 4. Elevation Geometry

原 SmoothedRoute2D 只读 lift 到 Layer 0。移动路线的结构为原层直线前缀、上升 cosine、Layer 1 中段、下降 cosine、原层直线后缀。端口保持原 XY 且 z=0；固定高层段与两过渡的 XY 投影保持原路线，不做 XY rerouting。

上升和下降可以在同一长直线上，也可以在目标前后的不同直线上。两窗口间的圆弧整体改变 z，保留圆心 XY、radius、sweep、源端点和长度；不切圆弧。窗口外保持原层。高层段覆盖本 pair 全部保存 CROSS 位置；不是把整条路线永久放高层，也不强制抬升与冲突无关的大部分长度。

## 5. Transition Run

沿用 9-B 的真实曲率公式：`minimum_xy_run_for_radius(dz,R)=pi*sqrt(R*abs(dz)/2)`。本次理论最小 run 约 4.96729413289805 mm，构造采用乘 `(1+1e-9)` 的微小数值余量，实际约 4.96729413786535 mm。上升、下降各一段；构造后再次检查实际水平长度和真实 R_min，而不是只相信计划值。

三组暂选候选最小 R_min 约 5.00000001 mm，均满足显式 5 mm。方向连接使用 9-B 的单位切向一致性，即 C1_DIRECTION/G1；不宣称参数导数大小或曲率在接点连续。

## 6. Transition Window Selection

从保存的 physical CROSS 点反查其位于移动路线的哪些 primitive/参数，覆盖最早到最晚目标交点。只在其前后 Line 范围选择窗口，保留 `max(1e-7,clearance)` 的沿线长度余量作为有限候选设计参数；该余量不作为安全证明，最终必须通过 9-C 距离检查。

每个足够长的可用区间取最前、中间、最后三种确定位置；枚举上升/下降窗口笛卡尔积，不做连续优化。有合法 Line 区域但长度不足返回 INSUFFICIENT_TRANSITION_SPACE；缺少一侧合法区域返回 NO_VALID_TRANSITION_WINDOW。

## 7. Candidate Construction

`ElevationCandidate3D` 保存 route_id、target_pair、全部 target_crossing、起止层、rise/fall/elevated 端点、窗口索引/参数、run、delta_z、required/minimum radius、原长/新长/增量、高层平面长度与完整 Route3D。升降段各两端精确落在原直线上，构造器验证 C0。

每组分别尝试移动 pair 两端的路线，但每个候选只移动其中一条。对 0 路线枚举 9 个候选，对 24/25/26 路线各枚举 36 个；每组共 45 个，三组共 135 个。

候选稳定排序先看目标冲突是否消除，再按过渡数、extra length、高层长度、窗口元组；全邻线新冲突数在初排时未知，明确为 null，不伪装为零。只对每组暂选候选做 511 邻线验证，本次三者新增碰撞都为零，因此没有必要以邻线计数区分它们。未声称对全部候选按邻线碰撞数完成最优排序。长度直接用 double 比较，微小舍入差可能先于高层长度决定次序；不宣称所得窗口最短或最优。

## 8. Acceptance Rules

目标 pair 验收同时要求：原端点不变；Route3D 有效且 C0；所有接点方向连续；两 cosine 真 R_min 达标；self-clearance 为 CLEAR；原 pair 为 COLLISION；新 pair 为 CLEAR。INVALID、NOT_CONVERGED、AMBIGUOUS 和 THRESHOLD 都不作为通过。

邻线复核另要求目标已消除、after collision count 不大于 before count、没有未解决状态。本次三组均严格减少且无新碰撞。`ACCEPTED_TARGET_PAIR_ONLY` 是局部候选状态；最终邻线接受证据在 local_validation 文件中，不覆盖或伪造初始评估字段。

## 9. Synthetic Fixture

A=(-20,0,0)→(20,0,0)，B=(0,-20,0)→(0,20,0)，原同层相交。仅移动 B，在中央插入上升/高层/下降；目标由 COLLISION 变 CLEAR，最近距离 1 mm。B 两端仍为 z=0，XY 原样，C0 与切向方向通过，self-clearance CLEAR。新增长度约 0.24389191746910 mm，两个 cosine，R_min≈5.00000001 mm。有限候选为 9 个。

## 10. Real CROSS Pair Probes

读取 `step_8_5_legacy_512_plot_geometry.json` 及 `step_8_5_legacy_512_physical_events.jsonl`，要求存在该 pair 的保存 CROSS，并再次调用现有二维 kernel 确认真实交叉；没有按 route ID 硬编码成功结果。输入哈希保存在 probe_summary。

| pair | 暂选移动路线 | 原/新目标状态 | 新最小距离 mm | 目标通过候选数 |
|---|---|---|---|---|
| 0 / 24 | 24 | COLLISION → CLEAR | 1 | 20 / 45 |
| 0 / 25 | 0 | COLLISION → CLEAR | 1 | 20 / 45 |
| 0 / 26 | 26 | COLLISION → CLEAR | 1 | 20 / 45 |

三组均成功。每组的 20 个通过候选分别来自移动 0 的 4 个和移动另一条路线的 16 个。其余 25 个因 SELF_AMBIGUOUS_CLEARANCE 拒绝，三组共 75 个，不放宽自检规则换取通过。

## 11. Local Collision Validation

每组暂选候选分别对其余全部 511 条原层路线做 before/after clearance，共 1533 个邻线比较、3066 次 route-pair 分析。各实验使用同一原始 baseline，不同时应用三组候选。

| pair / 移动路线 | before 碰撞邻线数 | after 碰撞邻线数 | 新增碰撞 | 消除碰撞 | 未决状态 |
|---|---:|---:|---:|---:|---:|
| 0/24，移动24 | 230 | 217 | 0 | 13 | 0 |
| 0/25，移动0 | 95 | 52 | 0 | 43 | 0 |
| 0/26，移动26 | 230 | 217 | 0 | 13 | 0 |

`new_collision_count` 指 after 的碰撞邻线总数；`new_collisions_created=after_set-before_set` 指新增碰撞 ID；`old_collisions_removed=before_set-after_set` 指消除碰撞 ID。逐邻线状态与距离均保存在 local_validation JSON，不把这两种计数混为一谈。

这是 clearance=0.1 mm 下的中心线违规邻线计数，不是二维 physical CROSS 数，也不是 multi 数。所有 after 状态均为 CLEAR 或 COLLISION；仍有 217/52/217 个碰撞邻线，不能称全局安全。

## 12. Length Overhead

| pair | 原长 mm | 新长 mm | extra mm | 高层平面长度 mm |
|---|---:|---:|---:|---:|
| 0/24 | 197.707963267949 | 197.951855185418 | 0.243891917469 | 0.2 |
| 0/25 | 156.707963267949 | 156.951855185418 | 0.243891917469 | 81.740669130084 |
| 0/26 | 197.707963267949 | 197.951855185418 | 0.243891917469 | 0.2 |

高层平面长度不含升降段。短高层段仍经过完整目标和邻线距离核验；仅凭覆盖二维交点不能接受。长度为现有 primitive 解析/自适应积分统计，没有推导真实插损。

## 13. Failure Modes

稳定失败包括无合法 Line 区域、水平空间不足、窗口重叠、目标未覆盖、目标点不在路线、非法配置、端点/接点/曲率不符、self collision 或自检未决、目标未清除。窗口不足与无窗口有独立测试；实际真实候选的拒绝原因是 SELF_AMBIGUOUS_CLEARANCE。9-C 相邻自检仅豁免正常接点；无法证明无额外接触时拒绝，不修改 9-C。

本次无 NEW_COLLISION_CREATED；若邻线复核出现新增碰撞，必须保留集合和 before/after 总数，不自动将目标通过等同邻线通过。未实现失败后的迭代 reroute 或多路线联合移动。

## 14. Tests

**656/656 PASS：历史 623 项 + 新增 33 项。** 新测试覆盖两层配置、重复 ID/z、显式参数、run 公式、足够/不足/无窗口、端口、升降、固定高层、C0、C1_DIRECTION、真实 radius、目标消除、自检、synthetic、失败稳定性、只读、长度、XY 保留、Arc 不切割以及未知邻线计数不得假报零。另有脚本中的三组真实 CROSS 确认、保存输入哈希不变和 511 邻线集成验证。

复现：`.venv\Scripts\python.exe -B scripts\validate_layer_assignment_3d.py . . <输出目录>`；仅测试可追加 `--tests-only`。完整 probe 本次约 68.6 s；最终 656 项测试约 5.1 s。时间仅为当前机器和案例证据，不是 512/1024 全局性能承诺。文件完整性证据列出阶段前全部记录文件及新增交付文件哈希。

## 15. Limitations

本次两层数值均为实验值；没有选定正式制造参数。目标窗口搜索有限，不保证找到所有可行解；并未对全部候选执行邻线排名。相邻自检沿用 9-C 的额外接触检查策略，不宣称连续接点附近满足正 clearance。过渡距离使用 9-C 数值误差保护，非任意坐标尺度的形式化区间证明。

511 邻线全部固定在原层；没有同时应用多个 elevation，因此不能推断多个候选叠加后仍安全。剩余 clearance collision 尚多。不存在正式 commit、512 全量 layer assignment、1024 数据生成或 routing、Arc 切割、loss optimization、GUI/GDS、依赖安装。

## 16. Verdict

**Step 9-D：PASS。** 已证明保存二维冲突可通过保持端口和 XY 的单路线合法 cosine 抬层消除；3/3 真实 pair 通过目标及选定候选邻线复核，零新增碰撞，碰撞邻线严格减少。结论只适用于三次独立实验，不作为正式全局解提交。二维 allocator 与历史成果未修改。

## 17. Recommended Next Step

建议下一 Step 专门研究多次单路线 elevation 的状态管理与候选相互影响：先定义显式配置、只读 proposed state、对已抬层路线的重新核验和失败回退，用小规模固定案例验证，再决定是否扩大。正式层间距与 clearance 仍须另行确定。此处仅建议，不启动下一 Step。
