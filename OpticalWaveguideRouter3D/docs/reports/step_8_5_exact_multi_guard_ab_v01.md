# Step 8.5-L：Exact-Geometry Multi-Crossing Guard A/B Experiment V0.2

日期：2026-09-10。文件名保留任务建议的v01后缀，实验语义为本次V0.2。

## 实验边界

正式baseline仍为A+G1+S1、top-U primary ascending。本实验G0/G1均固定descending，仅改变guard OFF/ON。Grid pitch仍0.175mm，width=0.05mm，spacing=0.125mm，radius=5mm，容差1e-9mm。未实现K、hierarchy、fragment、track sharing、reroute、crossing loss、finite-width或3D。

G0在G1前独立完成130,816对解析几何检查，核对全部指定回归门槛；通过才执行G1。最终G1交点重新独立计算，不使用候选缓存验证候选缓存自身。

## IEEE paper evidence

书目信息（本次用户提供）：Zhijie Huang, Lin Ma, Wanjing Kuang, Ying Shi, Zuyuan He, “Automatic high-density polymer waveguide layout for on-board high-speed optical interconnect”, IEEE, 2020。

本节依据用户本次提供的论文摘录；在当前项目/资料范围未找到该IEEE原文PDF，本次没有把这些摘录标为独立核读全文所得，也没有据此推导新的物理参数。

- 流程图包含候选interval、Overlap or multi-crossing判断、Increase the interval后重试的反馈。
- 摘录列出increase Δy和reduce bending radius两种缓解思路。
- 本实验固定radius=5mm，仅按现有扫描顺序继续测试候选；称paper-consistent feedback behavior，不称旧程序精确复现。没有证据确认旧程序每次增加恰好一个pitch。
- 本guard只拒绝现有multi判据明确成立的候选，不新增overlap拒绝。普通single crossing、double、angle均不是拒绝条件，因此也不是流程图全部约束的复现。
- IEEE Table I的Pitch=125μm与本科论文/current G1的0.175mm存在资料冲突。本Step没有修改grid；参数冲突留待独立审计。
- 摘录提供straight loss=0.05dB/cm、90° crossover约0.018dB及angle>20°不超过0.01dB的描述，缺少完整angle→loss数据且语义不完全一致。

“IEEE paper provides partial crossing-loss evidence, but insufficient for current full-angle model.” 本次未调用crossing_loss，保留其NotImplementedError。已知非交叉损耗不是total optical loss。

## 实现与候选生命周期

新增 `src/multi_crossing_guard.py`；`assign_tracks_2d`只增加可选guard参数，默认None走原分配分支。四类ordinary均可进入guard；原跨度检查失败的58条special-Z不进入guard，其独立解析几何只在最终post阶段加入。

每个未占用candidate依次生成临时骨架、真实Line/Arc曲线，计算candidate与每条committed普通路径的解析事件和physical consolidation。维护existing-existing完整pair cache及cross缓存。只枚举candidate的cross邻居之间存在AB cross的三角形，直接调用 `src/multi_crossing.py::classify_multi_crossing`，不重写阈值算法。

明确multi则拒绝，记录canonical最小witness，继续原scan；不移动已提交路径、不占用失败track、不更新失败几何/交点缓存。接受才commit；stale或rejected evaluation不能commit。boundary/outside允许并累计diagnostic，绝不宣称其安全。缺少可用track如实no_available_track，没有自动关闭guard或半径回退。

每次检查统计全部候选三角形，没有在发现第一个witness后提早停止；因此diagnostic完整，但成本可能较高。witness选择按canonical三元组最小值，确定性不依赖缓存插入顺序。

## 指标口径

- candidate_attempt_count：经过occupancy基础筛选的空闲track试放次数；occupied位置计入allocator_base_checks，不计guard尝试。
- guard_multi_rejections：被明确multi拒绝的candidate数量，不是检测到的全部multi三元组数量。
- boundary/outside observations：候选试放期间的观测次数，可重复出现，不是最终唯一三元组数。
- rejected_then_later_assigned：至少被拒绝一次、后来成功的唯一波导数；不同于所有发生track位移的波导数。
- track位移相对G0同一波导计算；abs统计包含未移动波导的零值，按四类另列。实际拒绝的空闲candidate数作为继续scan的观测量，不称旧Δy实现。
- eliminated：Step J triplet在G1不再属于当前multi集合，不表示三个交叉全部消失。存在未分配成员时单独not_comparable，不混记为消除。
- 最终ordinary-only multi由全量重新计算的交点中按triplet成员过滤得到；每对事件与是否加入special无关。因此这是独立ordinary子集检查。
- 性能为当前机器wall time；测试曾与实验并行执行，数值用于本次成本记录，不是隔离性能基准。

## 测试

新增29项，现有377项，总计406项全部通过。包括真实Line交点multi、单cross、一短边、boundary、outside、真实Arc double放行、无邻居/单邻居、拒绝不污染几何和pair缓存、接受才提交、stale拒绝、四类scan继续、特殊路径跳过、exclusive、确定性、耗尽不回退及ordinary不变量。

四类scan生命周期测试用合成witness隔离分配器行为；数学判据另由真实Line/Arc测试和真实512独立post验证覆盖。真实全数据descending+OFF回归另由G0 gate验证，不用小fixture替代它。

输出测试明细：`outputs/step_8_5_exact_multi_guard_tests.json`。

## 本轮停止记录

按用户指令立即停止长时间G1实验，不再运行完整G1、不启动其他重计算。已有代码、测试、G0结果和报告草稿保留，不回滚、不删除。

本轮结论仅为：

- G0 gate通过。
- guard单元实现完成。
- 406/406 tests通过。
- 当前G1全量candidate诊断实现性能成本过高，未完成，因此不能给出G1最终结论。

本报告为未完成实验的保留草稿，不支持据此作出G1收益或正式采用结论。
## Fast Rejection Path Refactor（本轮最新状态）

本节追加于上一轮中止记录之后。前文描述的full candidate diagnostics是历史实现，不删除、不改写为从未发生；当前代码已采用以下策略。本轮仍为Step 8.5-L，未进入M。

1. `get_single_cross_or_none`复用原physical intersection kernel，只返回唯一CROSS点或None。None表示没有唯一CROSS，缓存不保留事件列表、切向量或角度。没有复制Line/Arc求交算法。
2. 已提交pair缓存为unordered pair→Point2D/None，同时维护single-cross adjacency。candidate按确定的ID顺序逐步建立S(C)。每加入一个single neighbor，只检查其邻接集合与已发现S(C)的交集，不枚举全部existing-existing组合。
3. 继续调用原 `classify_multi_crossing`；首个明确multi witness立即返回。既不找第二个witness，也不继续测试尚未需要的candidate-existing pair。当前witness是确定性发现顺序中的第一个，不再要求全体witness中的最小值。
4. boundary和outside不再实时累计报告诊断；没有明确multi就不拒绝。普通single/double/angle依旧不是硬约束。
5. 拒绝时几何、occupancy、assignment、pair缓存和邻接索引不变；接受且完整、未过期的evaluation才更新缓存与索引。被短路拒绝的临时pair字典可以是不完整的，但不能commit。
6. final统计与candidate阶段分离。正式ascending默认、A exclusive、G1 pitch=0.175、radius=5、0.125阈值及58条special-Z规则全部保持。

语义细节：现有multi detector只统计kind=cross。因此一个pair若恰有一个CROSS，同时有TOUCH，wrapper仍保留该CROSS，不因TOUCH擅自改变原有eligible判据；纯TOUCH/OVERLAP或2+ CROSS不作为single neighbor。相关回归测试已覆盖。

### G0处理与代码范围

复用已经通过的 `step_8_5_exact_multi_guard_g0_gate.json`，没有重做G0完整交点、多交叉或损耗分析。本轮只做快速guard-OFF allocator检查（454 assigned、58 unsupported）和完整单元回归。`src/router_2d.py`本轮未修改，共用分配路径未改动。

修改：`src/multi_crossing_guard.py`、`tests/test_multi_crossing_guard.py`、本报告。

新增本轮工具：

- `scripts/run_exact_multi_guard_fast.py`：routing单独执行、15秒进度、可配置时间上限；不自动运行validator。
- `scripts/validate_exact_multi_guard_fast.py`：读取冻结几何，先ordinary，再global独立验证；不读取candidate verdict/cache。
- `scripts/benchmark_exact_multi_guard_fast.py`：仅固定小规模benchmark/profile。

旧完整诊断源码保留在 `outputs/step_8_5_exact_multi_guard_full_diagnostic_reference.txt`，仅供局部性能比较。旧实验脚本保留为历史脚本；本轮使用上述分离入口，没有调用旧一体化main。

## Performance Bottleneck

### 有界真实routing试运行

运行前明确采用180秒上限，作为本次性能可接受性的试运行门槛；这不是论文参数或新routing约束。时间门槛触发时停止整个实验，不接受正在尝试的candidate，不继续未完成波导，不把部分结果当完整布局。

| 指标 | 本次实测 |
|---|---:|
| routing完成 | 否，性能上限停止 |
| routing wall time | 180.018080 s |
| 已commit ordinary | 217（不是最终布通率） |
| 已确认guard exhausted | 21（不是其余波导全部失败） |
| candidate attempts | 14,914 |
| guard evaluations | 14,913 |
| explicit multi rejections | 14,696 |
| 唯一曾被拒绝的waveguide | 23 |
| rejected then success | 1 |
| candidate-existing pair tests | 1,002,357 |
| single-cross neighbor观测 | 438,818 |
| cached triangle检查 | 3,041,448 |
| 平均candidate evaluation | 0.011995653 s |
| 最大candidate evaluation | 0.039549200 s |

attempts比evaluations多1：最后一个候选在进入guard时触发时间上限，尚未执行求交，未commit。14,913=217接受+14,696拒绝。未处理或未完成成员不能记作assigned、failed或eliminated；完整assignments为null，冻结文件明确使用partial名称。

已耗尽ID：451、427、428、430、431、432、506、444、445、441、442、433、457、265、226、227、228、165、216、217、218。这些已完成各自扫描并拒绝所有可用候选；停止不是它们耗尽的原因。当前部分结果已经显示资源/判据tradeoff，但不外推剩余波导结果。

| 耗时部分 | 秒 |
|---|---:|
| candidate pair kernel | 155.685421 |
| triplet guard evaluation | 22.033331 |
| 全candidate evaluation（包含以上部分，不重复相加） | 178.891178 |
| temporary skeleton construction | 0.262020 |
| temporary smoothing | 0.364273 |
| reject/commit | 0.357128 |
| allocator基础占用检查 | 0.010121 |

真实运行约86.5% wall time仍在pair kernel；不是报告表格、loss或angle histogram。虽然不再保留完整pair事件，当前wrapper仍调用现有完整pair kernel/consolidation，因此底层仍会临时构造事件和计算局部切线/角度。没有把它误称为完全消除了pair内部计算。它保证数学一致性，但仍有性能限制；本轮止于profile，未进一步改写kernel或增加空间剪枝。

### 旧路径与新路径的实测小样本比较

固定workload：40条已提交直线（20水平+20竖直）、一条对角candidate，重复30次；两实现得到相同witness。准备状态不计入测量。没有重新完整运行旧512慢实验。

| 指标（每次evaluation） | 旧full diagnostic | 新fast rejection |
|---|---:|---:|
| median time | 0.003903450 s | 0.000528450 s |
| candidate-existing pair tests | 40 | 21 |
| triplet evaluations | 400 | 1 |

该固定小样本的median加速比约7.3866倍。它只证明此workload上的改善，**不是完整512 routing加速比**，不能与上一轮被人工中止的总时长直接算倍率。profile另记录10次fast evaluation，主要成本仍位于physical pair kernel及其验证/consolidation调用。

改善来自：报告级diagnostics移出candidate；只建立single-cross邻居；复用cached adjacency；首witness短路；完整heavy validation从候选循环中移出，计划仅在完成routing后执行必要的ordinary/global两阶段，而非每次候选重复执行。由于本轮routing未完成，真实数据的final heavy validation实际执行次数为0。

## Final Independent Validation

独立入口仅接收冻结的route geometry，不接收guard verdict、pair cache或single-cross graph。逐pair调用相同底层kernel重建事件，再运行原multi detector。ordinary共454条时，应检查102,831对；ordinary-only multi=0且自交检查通过后，才加入58条固定special-Z并重新检查130,816对。

本轮未达到完整routing条件，**没有执行真实G1 ordinary/global final validation**。因此以下值全部未确认，不填写0，不沿用G0冒充G1：

- ordinary-only independent multi；
- global multi、boundary/outside、自交；
- Step J 141 added消除数、新增multi；
- double、topU-topU、physical cross、cross pairs；
- angle、known non-crossing loss、最终track displacement。

已有G0仍为ordinary multi=240、global multi=345、double=4530、topU-topU double=0、physical cross=52129、cross pairs=47599、<20°=984、mean angle≈79.821642°、known loss mean≈5.264615825627/max≈6.187414816340dB。本轮不能填入对应G1差分。

独立validator的小型测试已验证：guard接受的三条几何独立检查为0；刻意损坏最终几何后，即使旧guard状态对应安全几何，validator仍检出1个multi；测试禁止调用guard evaluate，确保不以旧verdict作结论。这证明测试用例下的独立性，不替代真实454/512验证。

### 测试与交付

保留并适配406项旧测试，本轮新增12项：总计418/418通过。原geometry/collision/physical kernel均未改动；guard OFF、四类扫描、special排除、事务规则继续通过。

主要输出：

- `outputs/step_8_5_exact_multi_guard_fast_routing.json`
- `outputs/step_8_5_exact_multi_guard_fast_partial_geometry.json`
- `outputs/step_8_5_exact_multi_guard_fast_rejections.jsonl`
- `outputs/step_8_5_exact_multi_guard_fast_tests.json`
- `outputs/step_8_5_exact_multi_guard_fast_benchmark.json`
- `outputs/step_8_5_exact_multi_guard_fast_local_profile.txt`

试运行结束前核对既有输出与两个输入源哈希未变化；未删除、回滚或覆盖上一轮G0与中止记录。未生成完整G1 SVG、global统计或最终adoption结论。当前结论是fast path在固定小样本上更快，但真实routing仍未在本轮时间门槛内完成，且已有21个真实exhausted；暂不支持正式采用，也未进入Step 8.5-M。
## Exhaustion Correctness Audit（Step 8.5-L 最终审计，2026-09-11）

本节是本Step最终结论，保留前文full-diagnostic中止、fast-path重构与180秒试运行的全部历史。本轮未继续完整G1，未提高timeout，未优化或改写kernel，未改变guard判据、扫描、排序、pitch、radius或任何routing policy。

**审计结果：PASS。21条exhaustion均确认为当前具体规则下的真实候选耗尽。**

### 证据链与范围

输入为既有fast routing JSON、14,696条拒绝日志、217条partial committed geometry、原始512连接/端点快照及当前未改动的allocator/guard代码。源文件与旧输出哈希已核对保持不变。

1. 使用与allocator完全相同的固定排序，按保存几何恢复每条已提交路径的唯一track index；逐条重新生成几何并确认与保存曲线完全一致。217条已提交路径占用互不重复的track。
2. 从提交前缀重建每次失败时的800格occupancy；对所有已处理成功路径也检查“先前拒绝前缀+首个接受候选”与保存track一致。没有将后续提交的路径提前放入失败时刻。
3. 对每条exhausted route，拒绝日志的index序列恰好等于该时刻全部基础可用track的有序序列，无重复、漏扫或off-by-one；其余track确由前缀已提交路径占用。原跨度可用性检查均通过。
4. 对21条的**全部14,384次拒绝**，独立构造candidate与当时已commit的两个witness成员，重新计算三对Line/Arc physical intersections，并重新调用原 `classify_multi_crossing`。共43,152次witness pair重算，全部满足三对各恰一个CROSS、至少两边严格小于0.125-1e-9mm。这里不是102,831/130,816对最终布局验证。
5. 记录交点与独立重算的最大偏差约2.85e-14mm，边长最大偏差约2.79e-14mm，均远低于1e-9mm容差；未发现由stale witness或缓存错误产生的假拒绝。
6. timeout发生在后续route 219的未完成扫描；该route不在21条exhausted列表中，日志也仅覆盖其候选前缀。代码只有for-scan自然耗尽后才追加exhausted，BudgetExpired异常不会经过此分支。新增测试直接覆盖这种区分。

**证据限制：**上一轮没有保存原运行每条route入口/出口的cache checksum，不能声称本轮读取到了历史checksum。对21条的真实性确认依靠完整保存轨迹与全部独立witness证明；下面四条事务checksum来自按同一状态重建的局部重放。这个限制不改变“所有基础可用candidate均存在真实拒绝理由”的结论。

### Exhaustion transaction audit

局部重放仅到第四条exhausted route 430结束，不是完整G1。先前成功路径按保存曲线恢复，之前的拒绝按保存轨迹经过相同allocator分支；四个目标的每个候选实际调用当前fast guard和精确kernel。接受前缀的1,225个pair缓存从几何独立重建；邻接关系逐项核对与single-cross缓存一致。

对route **451、427、428、430**分别比较入口和耗尽后的：

- occupancy；
- committed assignments；
- committed geometry；
- pair cache；
- single-cross adjacency。

全部五类SHA256前后相等。四条重放候选序列及witness与原日志一致。合法新增的`no_available_track`失败结果和diagnostic记录不属于已提交路径残留；失败route没有track、没有几何、没有新增pair/adjacency。

route 451入口有44条已提交路径、946个pair缓存条目；427/428入口均49条、1,176条目；430入口50条、1,225条目。完整checksum见 `outputs/step_8_5_exact_multi_guard_exhaustion_summary.json`。

发现一个不影响状态或判定的文案问题：现有失败reason写作 `All tracks are occupied.`，但这里准确含义是“空闲候选全部被guard拒绝”。本轮仅审计，未修改该字符串；不能用这一文案代替真实occupancy和拒绝日志证据。

## First Exhausted Route Case Study

route **451**：top-U，PMT连接99—107。进入时44条committed占用track 799..756，剩余基础可用candidate为755..0，共**756个**，全部explicit multi拒绝；扫描方向和两个端点都完整覆盖。

完整candidate表：`outputs/step_8_5_exact_multi_guard_exhaustion_route_451_candidates.csv`。表中每行包含track index/y、verdict、witness A/B、canonical三元组、三个交点、三边、满足严格阈值的边标签、三对CROSS数量及独立检查结果。

以下展示首、中、末三个candidate；全部756个均已独立验证，不只是抽查。a/b/c按canonical route IDs解释，不能把字母位置误当candidate固定位置。

| track index | y(mm) | canonical IDs | 三边长度(mm) | 严格短边数 |
|---:|---:|---|---|---:|
| 755 | 137.15 | (95,288,451) | 0.077568261, 0.070296260, 0.020315201 | 3 |
| 377 | 71.0 | (95,288,451) | 0.066183281, 0.063750596, 0.017778869 | 3 |
| 0 | 5.025 | (95,288,451) | 0.066183281, 0.063750596, 0.017778869 | 3 |

首候选交点：Pab=(117.31124940419437,141.0)，Pac=(117.23624049305958,140.980238969431)，Pbc=(117.24095314404074,141.0)。中/末候选：Pab同前，Pac=(117.375,141.01777886924265)，Pbc=(117.375,141.0)。三对各一个CROSS，三条边均严格小于0.124999999mm；这是真实Line/Arc交点证据，不是guard缓存的自证。

## Why Full G1 Was Not Continued

21条失败已经完整扫描所有基础可用candidate，不是被180秒截断的route。当前策略不移动已提交路径、不重排、不重试失败route、不fallback；所以即使候选计算无限加速，这些已确认失败仍不会在同一执行中变成assigned。454/454验收已经失败，性能不是继续本Step的首要blocking issue。

此前事实继续保留：418/418测试通过、180.018秒bounded run、217 committed、21 exhausted、14,696 explicit rejection、小样本约7.39倍加速、pair kernel约86.5% wall time。其中217是中止时部分提交数量，不称最终布通率；14,384是21条失败自身的拒绝数，其余312次属于其他route，不混为exhaustion。

未进行完整ordinary 102,831对或global 130,816对验证，不再追求在完整布通前提已失败时填报正式final指标。G1 global multi、final double、final angle、final loss及正式G0→G1差分均保留：**N/A — incomplete routing**。

## Step 8.5-L Final Experimental Conclusion

**G1 FAILS ROUTABILITY REQUIREMENT。**

Fast rejection path substantially reduced candidate-level diagnostic overhead on the fixed local benchmark, but the exact-geometry greedy hard guard caused genuine track exhaustion under the current descending / exclusive-track / no-reroute configuration.

Therefore the guard cannot be adopted as the current routing baseline despite its locally correct multi-crossing rejection behavior.

准确含义：当前这一具体greedy hard-guard方案，在当前descending、exclusive track、radius=5mm、精确multi硬拒绝、无reroute和无fallback的组合下，不能同时满足multi avoidance与100% ordinary routability。本结论不扩展为所有算法或所有multi规避方案不可行，也不在此提出新的解决算法。

正式baseline仍为ascending A+G1+S1，guard默认OFF。Step 8.5-L以负实验结果结束；未进入Step 8.5-M。

### 测试与本轮文件

原418项测试继续通过，新增2项有效测试：完整候选扫描后才exhaustion、扫描中timeout不能误报exhaustion。最终**420/420通过**。本轮未改动任何src算法文件。

新增审计脚本：`scripts/audit_exact_multi_guard_exhaustion.py`；修改测试文件与本报告；新增输出summary、witness JSONL、451 CSV及测试JSON。审计脚本最初的事务探针位置错误已修正为实际route扫描入口；这是审计工具问题，不是allocator故障。新timeout测试也使用明确含多个候选的微型网格，避免单候选fixture无法触发第二次调用的错误。

### Exhaustion pattern / per-route table

| Route | Category | PMTs | Available | Explicit rejection | Occupied | First index | Last index |
|---:|---|---|---:|---:|---:|---:|---:|
| 451 | top-U | [99, 107] | 756 | 756 | 44 | 755 | 0 |
| 427 | top-U | [93, 107] | 751 | 751 | 49 | 750 | 0 |
| 428 | top-U | [93, 107] | 751 | 751 | 49 | 750 | 0 |
| 430 | top-U | [93, 107] | 750 | 750 | 50 | 749 | 0 |
| 431 | top-U | [93, 107] | 750 | 750 | 50 | 749 | 0 |
| 432 | top-U | [93, 107] | 750 | 750 | 50 | 749 | 0 |
| 506 | top-U | [117, 101] | 730 | 730 | 70 | 729 | 0 |
| 444 | top-U | [98, 117] | 729 | 729 | 71 | 728 | 0 |
| 445 | top-U | [98, 117] | 729 | 729 | 71 | 728 | 0 |
| 441 | top-U | [98, 113] | 718 | 718 | 82 | 717 | 0 |
| 442 | top-U | [98, 113] | 718 | 718 | 82 | 717 | 0 |
| 433 | top-U | [93, 113] | 718 | 718 | 82 | 717 | 0 |
| 457 | top-U | [101, 114] | 716 | 716 | 84 | 715 | 0 |
| 265 | top-U | [61, 114] | 715 | 715 | 85 | 714 | 0 |
| 226 | top->bottom Z | [51, 21] | 589 | 589 | 211 | 700 | 112 |
| 227 | top->bottom Z | [51, 21] | 589 | 589 | 211 | 700 | 112 |
| 228 | top->bottom Z | [51, 21] | 589 | 589 | 211 | 700 | 112 |
| 165 | top->bottom Z | [29, 57] | 587 | 587 | 213 | 698 | 112 |
| 216 | top->bottom Z | [49, 26] | 583 | 583 | 217 | 694 | 112 |
| 217 | top->bottom Z | [49, 26] | 583 | 583 | 217 | 694 | 112 |
| 218 | top->bottom Z | [49, 26] | 583 | 583 | 217 | 694 | 112 |

Category counts: top-U=14; bottom-U=0; top->bottom Z=7; bottom->top Z=0.
Same-PMT-pair clusters (descriptive only; not an algorithm proposal):
- PMT pair (21, 51): 3 exhausted routes, IDs [226, 227, 228].
- PMT pair (26, 49): 3 exhausted routes, IDs [216, 217, 218].
- PMT pair (29, 57): 1 exhausted routes, IDs [165].
- PMT pair (61, 114): 1 exhausted routes, IDs [265].
- PMT pair (93, 107): 5 exhausted routes, IDs [427, 428, 430, 431, 432].
- PMT pair (93, 113): 1 exhausted routes, IDs [433].
- PMT pair (98, 113): 2 exhausted routes, IDs [441, 442].
- PMT pair (98, 117): 2 exhausted routes, IDs [444, 445].
- PMT pair (99, 107): 1 exhausted routes, IDs [451].
- PMT pair (101, 114): 1 exhausted routes, IDs [457].
- PMT pair (101, 117): 1 exhausted routes, IDs [506].

Adjacent route-ID runs include 430-432, 444-445, 226-228 and 216-218. PMT ID numerical adjacency is not treated as geometric adjacency.
Audit runtime: 47.309 s; local replay: 38.277 s (audit replay only, not a new G1 experiment).
All 21 scans and 14,384 independent witness checks passed; transaction checks passed for 451/427/428/430.
