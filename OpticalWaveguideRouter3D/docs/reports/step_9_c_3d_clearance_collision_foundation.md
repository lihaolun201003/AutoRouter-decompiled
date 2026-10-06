# Step 9-C — 3D Clearance & Collision Foundation

## 1. Scope

结论：PASS（本阶段中心线距离与保守分类基础范围）。新增 `src/clearance_3d.py`、`tests/test_clearance_3d.py` 和可重现脚本 `scripts/validate_clearance_3d.py`，沿用 9-A/9-B 的三类 primitive 和 Route3D。正式二维 baseline 冻结；本阶段不做 layer assignment、rerouting、1024 routing、制造模型或优化，不安装依赖。

证据：`outputs/step_9_c_tests.json`、`outputs/step_9_c_clearance_validation.json`、`outputs/step_9_c_file_integrity.json`。所有数值来自当前代码执行和已保存二维输出。

## 2. Clearance Semantics

`clearance_mm` 必须显式输入，有限且非负，表示最小中心线间距要求。没有默认制造 clearance；二维 spacing、波导宽度、弯曲半径、layer spacing 均不自动映射到它。fixture 数值不构成正式层间距选择。

`COLLISION` 表示中心线间距小于 clearance，可能仍然空间不相交。真实相交另用 `intersection_status` 表达：有相交见证、沿用二维容差意义的相交、已证明分离或尚未解决。数值近零不冒充严格相交根证明。

## 3. Fixed-Layer Analytical Shortcut

两 primitive 严格固定 z 时，若 `abs(z1-z2) >= clearance_mm + tol`，`fixed_layer_clearance_certificate` 直接返回 `CLEAR_BY_LAYER_SEPARATION`。依据是任意两点距离不小于层高差；这是 O(1) 解析证书。

证书中的层高差仅为下界，`minimum_distance_mm=None`，不会伪装为真实最小距离。完整距离 API 为满足最近点和全局 minimum 输出仍计算平面距离，同时记录证书并判 CLEAR；它没有声称所有 route pair 已通过层证书跳过距离计算。倾斜直线不会被容差压平为固定层。

## 4. Line-Line 3D Distance

一般有限线段采用参数方形上的解析候选：四条边上的端点投影最小值，以及位于内部的驻点。叉积形式的分母避免近乎平行时 `1-dot²` 的消减；平行情况由边界候选覆盖。返回距离、两最近点及各自 [0,1] 参数，并处理 skew、parallel、crossing、endpoint minimum。公开 primitive 已拒绝退化线段。

## 5. Planar Primitive Distance

同层与异层固定 z 的 Line/Arc 统一投影到 XY，复用现有 `find_segment_intersections_2d`。已有 CROSS、TOUCH、OVERLAP 时沿用二维容差语义：同层距离为零，异层为层高差；实际见证点的微小偏差纳入上界。

未找到相交时补充有限 primitive 最小距离候选：端点到线/弧；Line-Arc 的圆心法向驻点且线投影、弧参数均合法；Arc-Arc 的圆心连线四组径向驻点且满足两弧范围。同心弧由端点到弧覆盖共同角区间。顺逆时针和角度环绕均处理。最终 `d3=hypot(d_xy_min, delta_z)`，不使用一般曲线优化器求固定层距离。

## 6. Transition Distance Method

Line×Transition、Arc×Transition、Transition×Transition 使用确定性参数矩形 branch-and-bound；倾斜 Line×Arc 也复用此路径。每个矩形求两弦有限线段距离，以真实曲线参数点距离提供上界，以弦距离减两曲线弦误差和 AABB 距离提供下界。优先细分下界最小单元；在该单元中细分弦误差较大的曲线，平局顺序固定。

对参数区间宽 h，二阶导上界 M2 给出线性插值误差 `M2*h²/8`。Cosine 的 `M2=pi²*abs(delta_z)/2`，故误差为 `pi²*abs(delta_z)*h²/16`；圆弧为 `radius*sweep_angle²*h²/8`，另计 lifting 保留端点与三角函数圆弧端点的残差；直线为零。两曲线与对应弦的点对距离之差不大于两误差之和，因此得到距离下界。

中点只补充真实点上界，不参与“平坦即安全”的推断。Cosine 整段中点可以恰好落在弦上，但全段并不直；专门测试覆盖该陷阱。达到 `upper-lower <= distance_tol` 才收敛，预算耗尽显式返回 `DISTANCE_NOT_CONVERGED`，保留 estimate、上下界、最近点参数和细分次数。

## 7. Numerical Error Policy

默认 `tol=1e-9 mm`、`distance_tol=1e-6 mm`、最多 4096 次细分；要求 `distance_tol>=2*tol`。解析距离加绝对浮点 guard；自适应下界减 tol、上界加 tol。以 `eps=max(d-lower,upper-d)` 给出保守对称误差，保留原始非对称区间。

`d-eps >= clearance` 才 CLEAR；`d+eps < clearance` 才 COLLISION。解析值与阈值在 tol 内时返回 TOUCHING_THRESHOLD，其他跨界区间返回 AMBIGUOUS_CLEARANCE；未收敛优先返回 NOT_CONVERGED。固定层独立解析证书可以直接证明 CLEAR。

几何弦误差界在实数运算下有依据，浮点 tol 是当前毫米尺度下的工程保护，并非采用向外舍入的形式化区间算术，不能外推到任意巨大坐标或病态输入。精确相交根未被全部求解，例如 Arc×Transition fixture 距离约 9.16e-16 mm、空间相交状态仍可 UNRESOLVED，但在 0.1 mm clearance 下可靠判间距不足。

## 8. Primitive Classification

输出包含六类状态 CLEAR、COLLISION、TOUCHING_THRESHOLD、AMBIGUOUS_CLEARANCE、DISTANCE_NOT_CONVERGED、INVALID_GEOMETRY，以及 minimum、margin、primitive 类型、最近点/参数、误差、方法和收敛信息。非法几何返回 INVALID_GEOMETRY；非法调用参数直接抛异常，不悄悄采用默认值。clearance=0 时相交点属于距离阈值边界，空间相交信息由独立字段表达。

## 9. Route3D Pair Clearance

`analyze_route3d_clearance` 遍历全部 primitive pair，记录索引及完整结果，汇总全局距离区间与最佳见证。任意 pair COLLISION 则 route pair COLLISION；无 collision 时，非法、未收敛、模糊或阈值状态不会变成 CLEAR。全局下界为各 pair 下界最小值，上界为各上界最小值。

最小见证的 primitive 索引不等于已证明唯一的数学最小者；另输出 `minimum_primitive_candidates` 和 `minimum_primitive_identity_certified`。区间不能排除的候选全部保留。存在非法 pair 时不宣称全局下界完整；空路线为非法几何。

## 10. Self-Clearance

策略为 `NONADJACENT_CLEARANCE_PLUS_ADJACENT_EXTRA_CONTACT_CHECK`：非相邻 primitive 完整检查 clearance；相邻 primitive 仅豁免正常接点，不直接跳过整对。固定同层采用既有二维 kernel 查找接点之外的交叉或 overlap；额外接触判 COLLISION。非平面相邻曲线若能以共同严格单调坐标证明只在接点相接，则豁免；否则返回 AMBIGUOUS_CLEARANCE。

连续曲线相邻段即使删去公共点，其距离下确界仍为零。因此本 API 不声称连接附近满足正 clearance，也不擅自引入裁剪长度。相邻结果明确 `positive_clearance_evaluated=False`；自检 minimum 仅针对实际求距的非相邻对，可能为 None。正常 Line→Transition→Line fixture CLEAR，非相邻交叉 COLLISION，额外相邻 overlap/第二交点可检出，未证明的非平面相邻情况保留模糊状态。

## 11. XY-Cross vs 3D-Collision Examples

A=(0,0,0)→(10,0,0)，B=(5,-5,z)→(5,5,z)，XY 正交相交。

| z (mm) | clearance (mm) | minimum (mm) | 结果 |
|---|---|---|---|
| 1 | 0.5 | 1 | CLEAR，层分离证书 |
| 1 | 1.5 | 1 | COLLISION，但空间 DISJOINT |
| 1 | 1 | 1 | TOUCHING_THRESHOLD |
| 0 | 0.1 | 0 | COLLISION，同层相交 |

近层 fixture：XY 最小间距 0.08 mm、层高差 0.05 mm，距离 `sqrt(0.08²+0.05²)=0.09433981132056604 mm`，clearance=0.1 时 COLLISION。

Cosine (0,0,0)→(10,0,1) 与 x=5、z=0.5 的横线在 t=0.5 内部相交，距离零。把横线提高至 z=0.65：自适应结果 0.1481830363217812 mm，12 次细分；区间 [0.14818299881149494, 0.1481830373217812] mm。独立标量公式 `(10t-5)²+((1-cos(pi*t))/2-0.65)²` 用 120 次黄金分割得到距离 0.14818303632178076 mm、t=0.5022993995075293，位于上述区间。此参考不调用生产距离算法。预算零时区间尚宽，正确返回 NOT_CONVERGED。

## 12. Lifted 2D Validation

读取 `step_8_5_legacy_512_plot_geometry.json` 与 `step_8_5_legacy_512_physical_events.jsonl`，选已保存交叉对及经既有 raw kernel 核验的非交叉对，同 lift 至测试 Layer(901,2.75)，显式 clearance=0.01 mm。

| route IDs | 二维结果 | 三维 minimum (mm) | 三维结果 |
|---|---|---|---|
| 0,24 | CROSS | 0 | COLLISION |
| 0,25 | CROSS | 0 | COLLISION |
| 0,26 | CROSS | 0 | COLLISION |
| 0,1 | 无相交 | 0.17499999999999716 | CLEAR |
| 0,2 | 无相交 | 0.3499999999999801 | CLEAR |
| 0,3 | 无相交 | 0.5249999999999915 | CLEAR |

六对共检查 150 primitive pairs；相交一致性全部通过，输入对象及源输出哈希不变。未运行 allocator，未宣称检查全部 512 路线组合。

## 13. Tests

623/623 PASS：原有 579 项全部保留并通过，新增 44 项。覆盖线段解析情形、同/异层、三类弧相关距离、三类 transition 配对、内部最小、确定性与误差区间、失败传播、阈值、route 最小索引、自检豁免及额外交点、lifting 和只读不变量。平面距离另有独立网格与速度界参考；transition 非零距离有独立标量参考。

可重现命令（项目根目录）：`.venv\Scripts\python.exe -B scripts\validate_clearance_3d.py . . <输出目录>`。脚本按现有项目测试风格执行 test 函数；逐项记录见 tests JSON。文件完整性证据覆盖阶段前记录的既有文件，新增文件单列哈希。

## 14. Performance

暂存验证 623 项测试耗时约 4.872 s。代表性固定层完整求距约 0.15–0.22 ms；上述非零 transition fixture 约 2.89 ms、12 次细分。运行时间依赖机器，仅为本次小规模诊断，不是 512/1024 全量性能承诺。仅用解析候选、AABB 和堆细分，没有空间索引、GPU 或新增依赖。

## 15. Limitations

尚未确定正式 clearance 或层间距；只处理中心线，没有实体宽度/截面/制造公差。自适应可预算耗尽或在阈值附近模糊；真实相交的严格零根不总能确定；浮点保护不是任意坐标尺度的形式证明。相邻自检只排除额外接触，不定义连接附近正 clearance。完整 route minimum 仍遍历 pair，层证书的快速布尔接口与完整求距接口职责不同。仅验证选定保存路线对，不运行全量 recovery 或 routing。

## 16. Verdict

Step 9-C：PASS，限定为显式中心线 clearance、解析固定层/线段距离、有误差和失败状态的 transition 距离、route 聚合与上述自检策略。阶段 checkpoint 即本报告及三个 JSON 证据文件；既有 2D allocator、9-A/9-B 源码、历史测试和正式输出保持原样。没有启动 9-D。

## 17. Recommended Next Step

建议 Step 9-D 先建立固定项目的显式层配置与约束输入契约，并设计最小 layer-assignment 方案：把层 z、允许过渡区域和中心线 clearance 分开输入，明确如何处理 AMBIGUOUS/NOT_CONVERGED 与自检连接策略，再制定小型验收 fixture。正式数值须来自项目需求，不能直接采用本阶段 fixture。此处仅建议，停止在 9-C。
