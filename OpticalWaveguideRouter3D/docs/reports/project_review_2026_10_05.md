# 项目审视与下一轮优化建议

日期：2026-10-05。范围：现有代码、Step 12–15 文档、A/B 原台账、修正版 C 与 D/E 保存产物。用户已确认真实 1024 端口数据尚未由导师或合作方提供。

本轮仅新增审视文档与只读分析产物，没有修改路由源代码、历史输入、实验参数或旧报告，也没有重跑完整优化或全量测试。重新统计保存的决策和近距集合，对保存终态的 7 对未决路线进行了定点间距分析，并重建检查了 512 全部 331 个自检歧义候选；还检查了测试收集与依赖环境。这不替代此前的全量复核。下述收益建议均需后续对照实验验证。

## 当前判断

项目已经具备固定输入上的解析几何、三维候选生成、保守间距检查、决策台账、保存重载及全量复核。下一步优先改进搜索覆盖与候选质量，同时准备真实输入接入。重定位、增加层数、GUI 和制造导出可以后置。

当前 1024 数据由历史 512 连线的双覆盖扩容得到：1024 条连接、2048 个端点、128 个 PMT，板尺寸 300×200 mm。它适合规模测试，真实数据收到后应作为独立输入验证。

来源：[固定输入生成器](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/src/fixed_1024_routing.py:24>)、[修正版输入配置](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/3d_strategy_v2_rev2/1024_c_fixed/config.json:4>)。

## 1. 优先处理静态生成失败的重复调度

| 规模 | 目标尝试 | 不同目标 | 重复尝试 | 候选评价 | 停止原因 |
| --- | ---: | ---: | ---: | ---: | --- |
| 512 修正版 C | 50 | 25 | 25 | 666 / 720 | TARGET_LIMIT |
| 1024 修正版 C | 310 | 165 | 145 | 8172 / 8172 | CANDIDATE_BUDGET_EXHAUSTED |

512 的 (290,433) 共尝试 14 次，(290,291) 共尝试 13 次，合计 25 次重复；这些尝试均为两条路线在两个目标层上 `INSUFFICIENT_TRANSITION_SPACE`，生成零候选。1024 的 (18,19) 共尝试 133 次，其他重复目标也为同类零候选失败。两规模全部 `NO_ACCEPTABLE_MOVE` 步骤都没有生成候选。

现有全局布局版本缓存保证了第三方变化后的动态验收正确性，应保留。增加独立的生成失败缓存：以冻结平面几何、实际锚点、目标层及候选配置为键，复用相同生成输入的结构性失败；涉及当前目标几何或锚点变化的情况必须重新生成。只有两个可移动 victim 均证明在相同生成输入下无候选时，才从待尝试集合中跳过该目标，且单独记录跳过次数。

不能直接恢复旧的“两条路线版本”失败缓存，也不能按失败次数永久禁止所有重试。验收失败中的新增邻居、未决邻居、净收益不足等仍需随全局布局变化重新判断。缓存命中若仍消耗目标尝试上限，就没有解决 512 的调度问题。

验证：静态失败不重复占用尝试；第三方变化仍触发动态失败重试；实际锚点或配置变化使生成缓存失效；双方路线中只有一方生成失败时另一方仍可尝试。随后以相同预算重跑新实验，检查终态与全量集合，不能预先承诺会恢复原 43,750。

来源：[缓存语义](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/src/strategy_v2_3d.py:71>)、[目标调度](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/src/strategy_v2_3d.py:464>)、[候选生成](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/src/layer_assignment_3d.py:130>)。独立重算见 [decision_audit.json](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/project_review_2026_10_05/decision_audit.json>)。

## 2. 诊断自检歧义，并让候选避开阈值边界

512 的 666 个已评价候选中，331 个带 `SELF_AMBIGUOUS_CLEARANCE`；1024 为 3927 / 8172，约占一半。这里的歧义不是已经证明的碰撞，仍应保守拒绝，但值得查清拒绝来源。

候选生成器当前用 `pad=max(1e-7, clearance_mm)/length` 留出窗口边距，可能把非相邻 primitive 的最小距离放在恰好 0.1 mm 的边界上。本轮重建 512 全部 331 个被拒候选行（312 个不同几何），全部仅有非相邻 primitive 距离在 0.1±1e-8 mm 附近的歧义，未发现相邻接触证明缺失。具体例子：第 2 步 target (9,34)、route 34、layer 1 的 candidate 0/1/2，弧与过渡之间由约 0.1 mm 短直线隔开，主要距离界为 [0.09999999899999432, 0.10000000099999432] mm，跨过阈值，因而无法证明严格 CLEAR。

证据含重建方法、数据/源码哈希与三个样本的窗口和 primitive 编号：[self_clearance_probe.json](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/project_review_2026_10_05/self_clearance_probe.json>)。1024 的 3927 个自检歧义候选本轮仅重算拒绝计数，未逐个重建，不能直接声称都属于相同原因。

下一轮先把拒绝细分为：非相邻距离界跨阈值、相邻额外接触未获证明、距离未收敛、确实自碰撞。对第一类尝试在候选窗口生成阶段增加明确的几何余量，并记录余量来源；保持 0.1 mm 判据和原有保守验收。余量可能减少可用窗口，需同时统计新增的“空间不足”拒绝。

相邻非平面 primitive 的证明分支不一定受更高细分预算影响；虽然它不是本轮 512 拒绝的来源，仍需在 1024 或其他输入诊断中区分。不能把所有歧义统一交给提高精度，也不能统一改判 CLEAR。完成诊断后再决定扩展证明或有限窗口采样。

来源：[窗口边距与三个位置](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/src/layer_assignment_3d.py:143>)、[候选自检](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/src/layer_assignment_3d.py:164>)、[相邻接触证明](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/src/clearance_3d.py:345>)。

## 3. 先准备真实输入契约和适配入口

通用 `load_connections`、`load_config` 仍为占位；现有实验主要从固定种子或历史快照进入。真实文件无法保证直接替换种子即可运行。

建议约定三类输入，并允许按合作方实际格式做映射：

| 输入 | 需要保留的信息 |
| --- | --- |
| 端口表 | endpoint_id、PMT/连接器 ID、真实槽位 ID、x/y/z、单位、所在边及端口方向；未知项明确缺失 |
| 连接表 | route_id、source_endpoint_id、destination_endpoint_id；保留连接身份和方向 |
| 配置 | 坐标原点与板边界、波导宽度、间隔的定义、半径约束、允许层高、输入来源和版本 |

导入后先给出计数、引用完整性、坐标有限性、重复/越界、缺失项和当前算法支持范围的审计，再进入布线。端口共享是否允许应按连接规约判断，不自动去重或改方向。

真实文件中的“1024”须确认指端口还是连接；现有 fixture 的 128 PMT×16、上下两侧、z=0 都不应成为真实数据的默认规则。当前二维分类器只接受上下边界上的 Point2D；其他边、非零端点 z、不同法向要明确适配。只有 Port1/Port2 的 PMT 连接表还缺端点坐标与槽位信息。

来源：[通用导入缺口](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/src/io.py:9>)、[旧连接表语义](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/src/io.py:24>)、[二维入口约束](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/src/router_2d.py:62>)、[固定 fixture 校验](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/src/fixed_1024_routing.py:75>)。

## 4. 性能优化先测候选验收

修正版 1024 的初始扫描约 67.25 s，分配阶段约 2158.04 s。4245 次全邻居候选验收各访问 1023 条其他路线，对应 4,342,635 次路线对分类调用；这不等于同样数量的昂贵 primitive 检测，因为现有 `pair_status` 已有 AABB 和固定 z 预筛。

首先记录候选生成、自检、目标检查、全邻居检查、排序与序列化各阶段耗时；用标准库 cProfile 找热点，再在无 profiler 的独立运行中比较总耗时。Python 官方明确区分 profiling 与 benchmarking：[The Python Profilers](https://docs.python.org/3.10/library/profile.html)。

低风险候选方向：复用同一目标尝试中不变的 before 报告；缓存完全相同候选的自身几何验证；缓存固定平面交点锚点；复用已计算目标检查时验证接口分类一致。路线对结果缓存必须以双方几何版本和检查配置为键，不能仅按 route_id。

源码已做增量集合更新和 AABB 预筛，无需把它们当作尚未实现的功能。进一步空间索引或 primitive 配对预筛须用原检测器核对集合完全一致，避免漏检。速度实验建议至少独立重复 3 次并报告中位数/范围，统一是否包含初扫、复核和输出写盘。

来源：[候选全邻居验收](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/src/strategy_v2_3d.py:179>)、[已有预筛](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/src/sequential_elevation_3d.py:30>)、[重复计算 before](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/src/layer_assignment_3d.py:170>)、[1024 台账](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/3d_strategy_v2_rev2/1024_c_fixed/ledger_C_fixed.json>)。

## 5. 补公平预算曲线与规则消融

512 先到目标尝试上限、1024 先耗尽候选预算，均不能据此声称收敛。建议保留历史记录，在新目录比较 0.5×、1×、2×候选预算；把目标上限作为单独变量，并报告每个停止条件。候选评价预算与实际耗时两种曲线分开展示。

B 的目标选择、双方候选比较、跨路线净收益排序尚未分别归因。使用相同初态、几何规则和预算，先做三个单项替换及完整 B；若存在明显交互，再补完整组合。所有配置使用同一评价器和最终复核。

另需明确候选预算在一个目标中间耗尽时的规则：当前主循环可从已完整验收的候选里提交最佳项，而 D/E 整个目标步骤回退。已提交路线的几何验收仍完整，但候选池比较可能未完成。下一轮统一或明确记录这种边界策略，并新增 `candidate_pool_complete` 等字段，避免把最佳已评价候选解释成双方完整候选池的最佳项。来源：[D/E 回退](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/src/strategy_v2_3d.py:313>)、[主循环选择](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/src/strategy_v2_3d.py:534>)。

独立实例优先于反复重跑同一个确定性实例来证明泛化。真实 1024 尚未收到时可增加预声明的合成拓扑作为压力测试，但明确标注合成来源；真实数据到来后单独作为外部验证，不根据其终态反复调参后再称独立验证。

## 6. 重定位后置，先分析未抬路线与二维起点

| 修正版 C 终态 | 双方未抬 | 仅一方已抬 | 双方已抬 | 总近距对 |
| --- | ---: | ---: | ---: | ---: |
| 512 | 43055（97.25%） | 1141 | 78 | 44274 |
| 1024 合成 | 123090（94.61%） | 3684 | 3324 | 130098 |

残余近距对主要仍在未抬路线之间，因此先解决首次抬升的窗口可行性、自检边界和调度覆盖更有依据。D/E 从 B 终态继续首次抬升也有改进，但使用了额外预算，不能直接据此认定新的调度更优。重定位目前只有本轮负结果，可作为后续支线。

项目 `src/opt2d/` 已做固定端点自由弯角和保护性局部优化，并非空白。它目前与三维流程独立。后续可比较“相同冻结端点下的原二维起点”和“优化二维起点”各自经过同一三维策略的结果；接口需保留解析段、路线 ID、端点与逐路半径，三维曲率约束单独明确。二维损耗评分下降不保证三维近距对下降，两套指标都要重算。

来源：[残余集合独立统计](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/project_review_2026_10_05/saved_state_audit.json>)、[二维优化现状](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_14_opt2d_frozen_robust_optimization.md>)。

## 7. 汇报与复现的确定性修订

原最终汇报有两处应以台账为准：

| 规模 | A 终态 / 额外长度 mm | B 终态 / 额外长度 mm | 修正版 C 终态 / 额外长度 mm |
| --- | --- | --- | --- |
| 512 | 45400 / 8.839448 | 43750 / 8.893004 | 44274 / 8.405220 |
| 1024 合成 | 138113 / 87.406597 | 130098 / 71.916944 | 130098 / 71.916944 |

512 B 的额外长度比 A 高约 0.053556 mm；修正版 512 C 与 B 也不并列。1024 B 与修正版 C 终态和额外长度相同，且两项均低于 A。原 512 C 与 B 并列属于旧记录，引用时须标版本。

修正版 PDF 构建脚本仍有“C 与 B 在两规模上的终态数值相同”的旧结论，文字报告也保留同句；建议修改说明后生成新版本，保留历史 PDF。来源：[PDF 结论文本](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/publication/report/brief_build/build_3d_strategy_v2_pdf_rev2.py:258>)、[文字报告](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_15_rev2_strategy_v2.md:70>)。

续跑长度口径也应补齐：`run_strategy_v2(..., allow_elevated_initial=True)` 的 `final_extra_length_mm` 实际相对续跑起点计算，不能解释为相对冻结二维路线的总额外长度。建议同时记录“本轮长度变化”和“相对二维基线的终态额外长度”，沿用 D/E 已有区分。来源：[长度账目](</C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/src/strategy_v2_3d.py:602>)。

本轮定点分析显示，512 修正版终态还有 3 对未决，1024 有 4 对，均为 `TOUCHING_THRESHOLD`。保存集合一致和复核 PASS 不意味着未决数为零；它们应继续与确定近距对分开记录，不通过放宽阈值消除。

README 和架构文档仍主要描述 Step 10、705 测试及旧入口；建议加入 Step 15 rev2 索引、真实/合成数据来源和当前可复现命令。统一实验 manifest，补解释器/依赖版本、配置、输入 hash、源码 hash、预算、停止原因；新实验输出目录防误覆盖。历史报告保留，并由新索引注明版本关系。

本轮确认 3D `.venv` 没有 scipy。对四个 opt2d 测试文件做 collect-only，它们都在模块级 `pytest.importorskip("scipy")` 被跳过；这是四个测试模块，不能理解成只略过四个独立用例。2D 项目的 `.venv` 已有 scipy 1.15.3，`src/opt2d/README.md` 指定使用该环境。建议统一测试入口分别执行并合并两套环境的结果，或建立包含所需依赖的完整环境；`requirements.txt` 当前未列 scipy 且未锁版本。本轮没有执行这些二维测试的完整用例，因此不新增其通过声明。

所有 0.1 mm 计数继续称中心线近距指标。几何诊断可补事件分型和长度分布；完整损耗、串扰和制造合规仍需平台约束与标定数据，不能用更多预算替代。

## 建议实施顺序

1. 静态生成失败缓存与调度跳过；同步回归验证动态失效语义。
2. 自检拒绝分类和候选窗口几何余量实验；阈值与验收规则保持明确。
3. 真实输入格式、校验器与数据入口；输入到来后先审计再路由。
4. 新目录做公平预算曲线、B 规则消融和候选验收性能测量。
5. 再做二维优化起点接入与有限窗口细化，最后决定是否继续重定位。

本轮分析产物：`outputs/project_review_2026_10_05/decision_audit.json`、`saved_state_audit.json`、`self_clearance_probe.json`。这些是保存产物的再分析，不是新的全量优化结果。
