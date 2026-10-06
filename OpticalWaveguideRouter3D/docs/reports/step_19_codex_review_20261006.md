# 三维光波导布线续跑结果审查

日期：2026-10-06。审查对象：DeepSeek 的 v8 续跑最终汇报及项目真实产物。历史代码、实验输出和报告保持原样；本文与审查证据独立保存。

## 本轮证明了什么

**本轮提供了更好的几何布线候选，但没有证明预测插损或实测插损降低。** 修复后的 G1 在主起点六个单元中，以相同实际评价次数减少了更多近距路线对，并降低了全布局的阶段长度增量。主 R2880 从 19,233 对、53.625801 mm 变为 18,211 对、30.096940 mm；同时逻辑升降过渡段由 356 增至 408。因此 G1 值得进入光学重评，但不能仅凭近距对与总长度决定损耗排序。

本轮仍按中心线近距对严格净减少验收，胜者以净减少量优先排序。材料、工艺、波长、芯形、折射率分布和收发条件没有冻结；没有新增经过标定的三维损耗模型、逐链路完整插损或串扰结果。几何 PASS 的证据边界没有改变。

**总体判断：几何研究有进展，光学研究尚未跨过标定与逐路重评这两道门槛。** 下一阶段应先修正支持链漏洞和报告口径，再重评已经保存的终态，不宜立即扩大优化矩阵。

## 证据支持的结论

### 四个值得保留的主起点终态

下表均为主起点、R 模式、实际追加评价 2880 次；长度是 512 条路线合计的阶段增量。E2/A/E 使用旧直线生成域，G1 使用新增路径窗口，不能把后者与 E/A 的差异解释成单一机制效应。G1 的目标上限为 200，其余表列 T2000；主起点 BASE 在 T200/T2000 结果相同。

| 终态 | 近距对 | 阶段增量 mm | 终态逻辑升降段 | 本轮可支持的判断 |
|---|---:|---:|---:|---|
| BASE E2 | 19,233 | 53.625801 | 356 | 同起点对照 |
| G1 修复版 | 18,211 | 30.096940 | 408 | 近距与长度两项改善，过渡段更多 |
| A T2000 | 18,042 | 71.946614 | 346 | 近距改善 1,191 对，长度多 18.320813 mm |
| E T2000 | 15,935 | 80.292495 | 418 | 近距最少，长度和过渡代价较高 |

来源：[P2 对照](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/overnight_3d_continuation/comparison/p2_g0_vs_g1.json>) 的主 R2880 单元、[P3](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/overnight_3d_continuation/comparison/p3_family_and_target_limit.json>) 的 `P3_A_FAMILY_T2000_R2880`、[E 对照](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/overnight_3d_continuation/comparison/pe_multi_anchor_limit.json>) 的 `PE_E_T2000_R2880`。独立重载四个终态并计算真实三维长度，全部与原账本吻合，误差小于 2×10⁻¹⁰ mm；详见 [轻量核验](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/codex_review_20261006/light_review_evidence.json>)。

### G1 的改善与适用范围

P2 的八个单元中 G1 有七个终态近距对更少。主起点六个单元的实际评价数均对齐；挑战起点只有预算上限相同：N 为 G0 2353 / G1 2489 次，R 为 G0 2481 / G1 2489 次。挑战 N 从 15,837 增至 16,232，挑战 R 从 16,537 降至 16,344。**“7/8 更好”只能表述为同预算上限结果，其中六个主单元还满足同实际评价量。** 挑战组不足以分离生成域效应与目标上限造成的提前终止。

旧 33 个无窗侧在本轮有限枚举下仍全部无候选。诊断归类为 23 个行程不足、10 个枚举窗口曲率不合格；但机制文件的 `legal_interval_mm`、`minimum_run_needed_mm`、`planar_total_length_mm` 为 null，不能据分类标签宣称已获得连续可行域上的无解证明。G1 确实执行了跨 primitive 的窗口；独立检查主 R2880 的 312 个路径升降窗中，只有 20 个含圆弧并跨 primitive，另外 292 个仍在单个直线片段上。因此尚未分离“允许跨弧”与“直线窗口长度、位置和 K16 前缀变化”的贡献。

G1 主 N/R2880 均执行 180 次首次抬升、0 次重定位，不能把两组收敛到同一终态写成重定位带来的改善。1296/1385 的路径窗口前缀占比来自冻结诊断集，不是正式全布局的评价占比。

![复用原 P2 对照图](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/overnight_3d_continuation/figures/v8_p2_g0_vs_g1_pairs.png>)

图 1 复用原始 P2 图，数据为上述 `p2_g0_vs_g1.json`。左图主起点实际评价量对齐；右图挑战起点只对齐预算上限。蓝/红及实/虚线在重合处会互相覆盖，具体 N/R 数值以数据文件为准。

### A 与长度约束

A 在主 R2880 实际用满 2880 次评价后仍改善，原先“未用满预算”的疑点在该对照中得到补证。但是“所有长度 cap 下 A 都不占优”是错误概括。

| 起点与模式 | cap mm | BASE 近距对 | A 近距对 | 判断 |
|---|---:|---:|---:|---|
| 主 R | 24 | 28,961 | 32,571 | BASE 更好 |
| 主 R | 40 | 23,031 | 26,747 | BASE 更好 |
| 主 R | 60 | 19,233 | 20,909 | BASE 更好 |
| 挑战 R | 60 | 16,285 | 15,408 | A 更好 877 对 |

全部受限对照是 12 个成对单元：BASE 胜 11 个，A 胜 1 个。例外中 BASE 实际阶段长度约 37.7555 mm，A 约 59.7701 mm，虽然共享 60 mm 上限，实际长度并不相等。它支持“在这一共同长度上限下 A 可更好”，不支持“同实际长度下 A 更好”。

来源：[P4 数据](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/overnight_3d_continuation/comparison/p4_length_cap.json>) 的 `capped`。代码先在 `used += 1` 扣评价预算，基本检查通过后才检查 cap，并单列拒绝；完整邻居验收与严格净减少仍保留，见 [引擎](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/src/overnight_engine_3d.py:819>)。

### E 与缓存计时

E T2000 主 N/R2880 均达到 15,935 对，实际评价均为 2880。汇报拿 R 的 E 对比 N 的 BASE 18,444，模式错配；正确 R 基线是 19,233。修正后 E 仍优于 BASE 和 A，排序不变，但 R 的改善量应为 3,298 对。

E 从 T200 的 668 次评价、32,565 对，变成 T2000 的 2880 次评价、15,935 对，证明上限截断确实限制了原配置。它没有证明多锚点机制本身无代价：主 R2880 T2000 有 1,933 次目标尝试，其中 1,743 次零候选；同时存在零候选缓存 key 的读写不一致，见后文。挑战 E T2000 仍在目标上限停止，N/R 实际只用 2008/2264 次评价，不能泛化“上限 2000 已经足够”。

P5 六次保存记录呈交替、互不重叠的运行区间，动作轨迹、终态几何及近距集合相同，长度台账也一致。缓存每次命中 8,160 次，内核中位数 OFF 478.852 s、ON 347.081 s，范围分别 456.699–560.610 / 308.898–546.351 s。可报告本次观察到中位数降低及计算复用；样本只有三次配对且波动较大，不能宣称稳定或普适加速。范围重叠本身也不是“没有效应”的统计证明。没有系统资源采样，因此只能确认保存的正式任务区间不重叠，不能证明整机没有其它负载。来源：[P5](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/overnight_3d_continuation/comparison/p5_serial_timing.json>) 与本次独立证据。

六次 P5 运行的 `code_version` 相同，但属于较早版本，路径窗口模块与驱动器哈希不同于 10:11 的顶层快照；它们使用 LINE_ONLY 并有逐步等价证据，结论限于这一实例，不覆盖修复版 G1 的运行速度。初始全扫在计时区间外，不能用这份计时报告扫描加速。

## 尚未测到或不可检验

本轮没有逐链路完整 IL 均值、P95、最大值、超预算条数及串扰分布；没有局部升降组件的校准传输，也没有传播、弯曲、交互和探头耦合参考面的统一定义。`src/loss.py` 的历史传播系数与二维弯曲表没有成为三维模型，`crossing_loss()` 仍未实现；默认配置的关键损耗项仍为 null。

为检查已有终态是否能直接重评，Codex 仅重载四个主 R2880 终态，重新计算了每条路线三维弧长与升降段数，没有运行优化或全布局路线对扫描。新增 [每路几何 CSV](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/codex_review_20261006/saved_route_lengths.csv>) 共 2048 条记录。

| 主 R2880 终态 | 每路阶段增长均值 mm | P95 mm | 最大 mm |
|---|---:|---:|---:|
| BASE E2 | 0.104738 | 0.678120 | 0.678120 |
| G1 | 0.058783 | 0.217168 | 0.678120 |
| A T2000 | 0.140521 | 0.678120 | 0.678120 |
| E T2000 | 0.156821 | 0.678120 | 0.678120 |

P95 采用排序后 `(n−1)×0.95` 位置的线性插值。上述是几何分布，不是插损分布。

G1 相对 BASE 的每路长度差：均值 −0.0459548 mm，P95 +0.0826166 mm，最大 +0.4342283 mm；132 路缩短、28 路变长、352 路不变。若仅采用历史未标定的 α=0.005 dB/mm，平均传播分项差为 −0.000229774 dB/路，而 P95 为 +0.000413083 dB/路、最大为 +0.002171141 dB/路。**这只是传播系数情景算术，没有升降、真实交叉、近接耦合或接收贡献，既不是净 IL 预测，也不是测量值。** 平均长度更好不保证每条路线更好。

余弦高度律仍未消除端部曲率跳变。路径窗口的三维曲率闭式与真实弧长实现有几何证据，但不能推出模态扰动或组件插损更低。GI 圆芯与 SI 矩形芯应按 [最新物理调研](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/3d_loss_model_research_20261006.md>) 及 [证据 JSON](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/references/core_physics/loss_model_evidence_20261006.json>) 分开；未知参数继续保持未知。

## 存在问题及其影响

### 支持链存在通用漏检，但尚未证实污染本轮终态

`analyze_route3d_self_clearance()` 只枚举顶层 primitive 之间的组合，没有检验一个多 piece `PathWindowTransition3D` 内部的非局部自近距。[代码](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/src/clearance_3d.py:517>)。

独立反例使用内部 C1 连续的一个路径升降窗，最小曲率半径约 10.0000058 mm；窗内两个非局部点的距离约 0.0478267 mm，小于 0.1 mm。把该窗作为路线唯一顶层 primitive 后，自近距检查返回 CLEAR、检查数为 0。这证明通用支持链声明不充分。

对正式修正版八组已执行窗口做了限定检查：窗口均为单 piece 或线—弧—线，内部 C1 失败 0；70 个内部非邻 piece 对的最小 XY 距离约 7.0711 mm，因此空间距离也不小于该值，未发现反例在本轮终态触发。**不能由通用漏洞直接宣布 G1 排序无效；但应在支持更多路径形状前修复，并补定向证据。** 构造、输入哈希和返回值见 [几何证据](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/codex_review_20261006/geometry_review_evidence.json>)。

邻接帽的参数切分使用 XY 弧长下界，却报告“真实三维弧长豁免 <0.4 mm”。合法 run=8 mm、dz=2 mm 的反例得到未检邻域弧长上确界约 0.400031665 mm。当前结论是证书口径不准确，尚未证明其造成实际空间近距漏判。

`minimum_path_run_for_curvature()` 的“exact minimum”和“kappa_xy≥1/R 无合法长度”说法也是错误的必要性外推。20 mm 直线—居中 R=5 mm 的 45° 弧—20 mm 切线、高差 1 mm 的窗口，真实最小三维半径约 5.00626036 mm，helper 却返回不可行。正式生成器并未调用这个 helper，而是检查实际 piece 两侧的精确曲率；因此该问题影响 helper 文档与测试解释，不能据此推翻正式 G1 曲率验收。

### E 的零候选缓存 key 不一致

`structural_zero_candidates_cached()` 读取缓存时只用 `dynamic_anchors`；生成及写入缓存时，多锚点 E 已加入 witness。两者的 key 不同，可能让原本可跳过的重复零候选再次消耗目标尝试上限。[读缓存](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/src/overnight_engine_3d.py:609>)、[写缓存](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/src/overnight_engine_3d.py:790>)。

它为 E 的高零候选尝试数提供了未排除的实现解释。已保存 E 的 15,935 对和当前算法排序仍有真实产物支持；修复缓存后的停止位置和排序尚未测量。应先做锚点一致性及缓存失效的定向复现，不宜直接把 T2000 的收益包装成多锚点已被全面验证。

### 验收与报告口径需要补证

当前 `final_verification.json` 的 110 行＝74 PASS＋36 引用。其中 PASS 包括首轮缺陷 G1 八组、修复 G1 八组、中立性八组、P3 十组、P4 二十四组、P5 六组、E 十组；不是 74 个互不重复的有效策略对照。缺陷版虽然接受后的几何能 PASS，却不能用于判定 G1 算法效果。

独立读取 74 行的 summary/ledger/recheck/config，保存字段一致；对 36 引用做 180 次来源哈希检查（140 个独立文件），均匹配。六份现行 manifest 与各自 SHA256 sidecar 匹配；1886 文件只是交付清单数量，Codex 独立核对了其中 32 个清单条目，未声称重验全部文件。G0 中立性实际有八个重跑终态与历史文件字节一致，而官方比较表只列三个。

原报告 §9 仍写 94＝64 PASS＋30 引用，且复核表不显示 tag，导致缺陷版和修复版同名重复；这是报告版本与标签遗漏，不影响已核对的数值排序。P4 全称结论及 E 的 R/N 基线错误需要在新报告更正，不能只修排版。

原始 `full_suite_frozen_code.log` 的 803 passed / 4 skipped 对应修复前快照（10:11 冻结、10:17 日志），25＋21＝46 项也是修复前针对性口径。边界吸附修复及新增四个参数化用例发生在其后。Codex 仅独立补跑端点四项：**4 passed / 25 deselected，0.87 s**，日志见 [端点回归](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/codex_review_20261006/boundary_endpoint_regression.log>)。这不等于修复后全量回归；缺少的版本对应关系必须如实披露。

末版 PDF 哈希 `94a5a034c258c6c60c58ff81d2eb7958b6bea09bcdc0056ec4192e93cffa3796` 与十四页页图记录匹配。但原 QA 脚本自动将所有页标为 inspected/OK，方法文字只明确关键页复核；缺失 ASCII 扫描记录时还会把 wraps 设成 0。这些字段不能单独充当完整目检及零拆行的原始证据。Codex 对末版已有页图另作独立检查，记录单独保存；不把此次补核写回 DeepSeek 原始 QA，也不把旧 32 页“检查完成但 13 页 ISSUE”称为全部版式通过。

本次已逐页查看当前十四页 PDF 的全部现有页图，并在内存重渲第 1/7/14 页，三页与现有 PNG 的 RGB 像素完全一致。没有发现裁切、压字、乱码或数字拆行；第十一页图字偏小，第十二页挑战散点无法清楚辨别 N/R，第十四页大面积留白，主结论到第十页才出现。正文还有上述标签与数值口径问题，不能只以版面通过称为报告验收完成。Word 未另行渲染，不能由 PDF 的检查追认 Word 视觉 QA。详情见 [独立 PDF 补核](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/codex_review_20261006/pdf_review_notes.md>)。

## 少量值得继续的研究假设

| 假设与机制 | 最小对照 | 证伪条件 |
|---|---|---|
| G1 的收益主要来自更长直线窗口与前缀竞争，而非跨圆弧本身 | 在既有冻结诊断目标上，区分 G0、G1 单 piece 直线窗、含弧窗；保留共同 K16，分析已保存胜者及前缀，不新跑布局 | 去掉含弧窗后原优势消失，且这种变化不能由直线窗口配置或同分排序解释，则“主要来自直线窗”不成立；证据不够时保留未知 |
| E 的目标上限敏感性部分来自多锚点缓存 key 失配 | 取两个已记录的重复零候选目标，固定同一布局/witness，核对 key 及布局或 witness 改变后的失效 | 锚点统一后 key 仍没有影响重复目标跳过，或这些空尝试均发生在真实不同的几何条件下，则该实现解释不成立 |
| G1 的净损耗收益取决于交互收益能否抵消新增组件及模态历史代价 | 用已保存 BASE/G1/A/E 四个主 R2880 终态建立每路事件台账；仅在同平台组件已标定时传递功率并报告完整 IL/XT | 在校准适用域与不确定度内，G1 均值/P95/最大 IL 没有改善，或串扰/制造条件恶化，则“几何改善可转化为低损耗优势”在该平台上不成立；缺校准时不可检验 |

优先完成支持链、缓存语义及每路几何事件。当前不需要新增通宵实验、成本排名全矩阵或组合策略。下一阶段完整任务见 [DeepSeek prompt](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/plans/prompt_deepseek_optical_revaluation_20261006.md>)。

## 审查操作与证据位置

本次只读取源代码与产物、核对来源哈希、重载四个既有布局的弧长、做三个局部几何反例及四项端点回归、检查已有图件。没有启动 DeepSeekHarness、优化组、后台监控、持续轮询或大规模复跑。

- [独立轻量证据](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/codex_review_20261006/light_review_evidence.json>)：四个终态长度、分位数、组件数、manifest 与清单子集。
- [矩阵审查证据](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/codex_review_20261006/matrix_review_evidence.json>)：74 行、36 引用、P4 例外、E key 与对照口径。
- [几何审查证据](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/codex_review_20261006/geometry_review_evidence.json>)：局部反例、本轮终态适用域、代码哈希。
- [每路几何数据](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/codex_review_20261006/saved_route_lengths.csv>)：完整 512 路×四个终态，保留路线 ID。
- [独立 PDF 补核记录](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/outputs/codex_review_20261006/pdf_review_notes.md>)：当前十四页的逐页观察与图件可读性限制。

本审查交付 Markdown，没有新增 Word/PDF；原报告保持不变。研究结论以真实 comparison/ledger/recheck 与上述限定核验为准。
