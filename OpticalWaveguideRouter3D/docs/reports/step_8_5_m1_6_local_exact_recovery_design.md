# Step 8.5-M1.6 — Local Exact-Geometry Recovery Design & Feasibility Specification

日期：2026-09-11。**PASS：设计与四类离线 feasibility 范围。没有正式 recovery commit。**

## 1. Scope

仅设计 single-victim exact recovery，并实现独立 sandbox evaluator、四个固定真实案例的完整候选扫描与必要验证。不修改正式 allocator，不执行完整318目标循环、迭代 reroute、depth-2/3、递归、fragment、shared track、integer K、半径/间距调整或后续三维功能。用户最后明确要求证据足够、停止扩大实验，本报告据此收尾。

事实来源为当前源码、保存输出及四份前序报告：step_8_5_exact_multi_guard_ab_v01.md、step_8_5_m_hierarchy_fragment_audit.md、step_8_5_m1_dynamic_d_diagnostic.md、step_8_5_m1_5_exact_multi_attribution.md。没有以聊天摘要覆盖它们，也没有新增论文原方法主张。

## 2. Current Baseline

正式 baseline 保持 **ascending + exclusive A + guard OFF**。width=0.05 mm、spacing=0.125 mm、pitch=0.175 mm、radius=5 mm、board height=150 mm。454 ordinary + 58 special-Z = 512 analytic routes；全局主集318 unique multi。

读取保存 plot geometry、physical events、multi JSONL、M1.5 summary/triplets/crosses，以及原始两个Excel快照。没有重新运行512 allocator。核对：318条唯一triplet、954行归因、512项per_route，参与计数总和954；保存physical CROSS为55,935，有CROSS的pair为49,502。physical events哈希与既有multi summary相符。所有318个目标以当前classify_multi_crossing复核通过；954个CSV交点与保存physical坐标逐值相同，且属于所引用的两条真实primitive。

从454条ordinary保存水平段恢复唯一track index；全部落在当前G1 grid，occupancy无重复。使用正式骨架与圆角构造器重建全部454条的原轨道几何，primitive类型、端点、圆心和sweep在现行1e-9容差内一致。保存plot由角度重建Arc会有浮点末位差别，因此不声称重建对象与原对象逐bit相等；原文件保持逐字节不变。

既有全pair coverage=130,816来自正式保存证据，本轮未再运行全局all-pairs baseline求交。boundary=2、outside-single-cross-assumption=841,477保留独立口径，均不是318主集。

## 3. Why Recovery Is Needed

Step L的21条exhaustion及14,384个独立有效witness仍成立；route451的756个候选均真实被拒。那是descending、exclusive、greedy/no-reroute的负实验，不是检测器错误，也不是全局无解证明。

M1.5分类为204 PAPER_LIKE、23 AMBIGUOUS、91 NON_PAPER_LIKE，说明不能把hierarchy或Dynamic-D当作所有目标的必要条件。通用Line+Arc局部恢复值得设计，但不得以此更换正式baseline。

## 4. Victim Selection Principle

**PROJECT-SPECIFIC：victim_score(R)=当前布局中包含R的unique multi数量，越少越先尝试。** 这是用户指定的局部影响范围启发式，不是论文原方法，也不是数学最优定理。

必须先过滤special等不可移动对象，再在ordinary中按score升序尝试。完整未来单次目标流程：第一victim扫描全部候选并选择其最佳严格改进；没有可接受候选才尝试第二、第三个可移动victim。不能跨victim以更低M_after覆盖既定优先顺序。每次未来成功提交后应使用新布局重新计数，不能继续使用本次318布局的固定score。

## 5. Victim Score Distribution

| 指标（分母318） | 数量 | 比例 |
|---|---:|---:|
| 唯一最低 | 241 | 75.79% |
| 最低并列 | 77 | 24.21% |
| 最低集合仅ordinary | 270 | 84.91% |
| 最低集合仅special | 29 | 9.12% |
| 最低集合ordinary/special混合 | 19 | 5.97% |
| 没有可移动ordinary | 0 | 0% |

最低集合含ordinary为289/318=90.88%，含special为48/318=15.09%；二者重叠19个，不能相加。最低仅special的29个目标，跳过special后的首ordinary score分布：2→2个、3→8、4→5、5→6、6→7、7→1。

| score | min频数 | middle频数 | max频数 |
|---:|---:|---:|---:|
| 1 | 77 | 13 | 1 |
| 2 | 84 | 41 | 7 |
| 3 | 59 | 63 | 22 |
| 4 | 63 | 90 | 47 |
| 5 | 20 | 46 | 59 |
| 6 | 12 | 37 | 47 |
| 7 | 3 | 19 | 41 |
| 8 | 0 | 6 | 50 |
| 9 | 0 | 3 | 6 |
| 12 | 0 | 0 | 12 |
| 13 | 0 | 0 | 26 |

min/middle/max均值为2.7264 / 4.1006 / 6.5063。较小score确实对应较少的旧multi依赖，这是描述性依据；它不限制新产生的multi数量，不证明更容易恢复或最终效果最优。

完整逐triplet三根计数、min/middle/max、最低并列集合、ordinary顺序保存在step_8_5_m1_6_victim_statistics.json和step_8_5_m1_6_victim_order.csv。

## 6. Tie Policy

推荐并在本次probe采用：**special排除 → multi_count升序 → 合法替代track数量降序 → route_id升序作为最终稳定顺序**。保留所有同score成员和原score，不把route_id解释为更安全。

当前800轨道、454占用，任一ordinary临时移除后有347个可试位置，其中346个是替代位置。固定端点、跨度已合格、G1上下边界预留radius，四类ordinary都可使用这同一集合，因此候选数量在本baseline中无法打破并列。route_id仅在这些指标全部相等时使复现确定，不是主要victim策略。

同时审计“局部角色”：77个最低并列目标中45个的最低成员具有不同unique co-participant数量。但较少co-participant是否更易恢复、是否减少新增multi，尚未对照验证；不把这个差异直接升格为安全证据，也不按未经验证的角色、左右危险侧或空间半径筛选victim。本轮不增加其他victim实验来决定它。

## 7. Candidate Track Semantics

直接复用build_track_grid_2d，y_i=5.025+i×0.175 mm，i=0…799，末格144.85 mm；上边界144.975不因取整而扩展。当前普通跨度要求abs(dx)≥2r−tol。bottom-U按i升序，其余ordinary按i降序枚举。

ascending指top-U primary排序，不能误写成所有track向上扫描。当前代码没有论文类别区域锁；恢复也不凭空加入。候选资格是移除victim后该格为空，且正式几何构造合法。原track允许回放作为negative control。不得使用其他ordinary占用位置，不允许fragment或共享。

扫描顺序只规定访问顺序；同一victim必须比较全部候选，不能遇到首个改进便结束并声称找到了该victim最小M_after。

## 8. Temporary Removal Transaction

本次使用copy-on-write：占用数组复制后只在副本释放victim；Waveguide与preparation深拷贝后构造candidate；geometry和511个pair结果仅存在局部新对象。基线geometry、assignment、pair/multi cache、route statistics不写入，因而正常拒绝、异常和返回后的rollback均为丢弃私有对象，没有“先改正式状态再反向修补”。

未来正式实现应将occupancy、assignments、geometry、pair cache、adjacency、multi index、route statistics、version放在一个状态根。候选基于version建立私有overlay；独立验证通过后先构造完整新状态，再比较version并原子交换状态根。旧version候选必须失效，任何半写入不能发布；持久化也须临时文件校验后原子替换。这里只规定事务方案，没有实现COMMIT API。

## 9. Exact Candidate Geometry

调用generate_assigned_routes_2d → smooth_orthogonal_route_2d(radius=5)，继续用validate_smoothed_route_2d、arc_segment_radius、find_smoothed_route_self_intersections_2d核验。显式检查首尾连接原始Port、连续性、非空、radius、合法Arc及非正常相邻接点的自交。不能将骨架碰撞替代真实Line/Arc评估。

全部1388候选在本次扫描中均通过几何检查，无candidate kernel异常。正式保存physical事件全部为CROSS，当前基线不存在保存的inter-route TOUCH/OVERLAP；本次候选也均未产生它们。检查只使用工程已有centerline exact分类，不引入有限宽度、制造间距或角度硬阈值。若未来输入基线已含异常，需明确异常身份与“新增”的比较语义，不能把本数据零异常前提泛化。

## 10. Local Intersection Delta

设移动R，所有其他route几何不变。pair(a,b)若a≠R且b≠R，其primitive输入、tol、physical consolidation均相同，结果不变；所以唯一可能变化的pair集合是{(R,j):j≠R}，共511对。

每候选完整重算这511对，保留每对所有physical事件及CROSS multiplicity，包括空结果；不能只查原邻居，也不能沿用Step L首witness短路，因为评分需要所有新增/删除multi。固定pair map只读。生产版可以保存完整星形overlay，明确空pair覆盖旧记录，不能以“键不存在”误复用旧交点。

## 11. Local Multi Delta

设B为旧318主集，B_R={t∈B:R∈t}。不含R的任意triplet三条边全部固定，其分类必不变。包含R的triplet则需要由候选交点重新判定，即使其中成员以前从未出现在B_R。

令S_R为candidate与之**恰有一个physical CROSS**的其他route。对S_R中每一对(a,b)，若固定pair(a,b)也恰有一个CROSS，调用现有classify_multi_crossing。得到新A_R。这覆盖所有可能eligible的含R三角形，不能只检查旧318目标或原multi邻居。

**B_after=(B−B_R)∪A_R；M_after=|B|−|B_R|+|A_R|。**

old_multi_removed=|B_R−A_R|，new_multi_created=|A_R−B_R|，所以M_after=M_before−removed+added。保存added/removed的canonical triplet身份以便独立比对。

实现保留multiplicity，因此double→single新eligible、single→double退出eligible均不会漏掉；一CROSS伴TOUCH仍按原multi criterion处理，另走异常验收。boundary/outside没有混入M；如未来需要更新其完整诊断，应在所有至少一CROSS邻居三角形上更新，不能从本single-neighbor集合声称拿到了完整outside差分。本轮未计算candidate全量boundary/outside统计。

## 12. Candidate Scoring

先通过endpoint、geometry、occupancy、special隔离和现有异常检查，再要求目标消失且M_after<M_before。可接受候选的稳定字典序为：

**(M_after, new_multi_created, abs(new_index−old_index), new_index)**。

第一个指标对应核心目标，第二个避免同净改善下无必要的新依赖，第三个优先较小轨道扰动，最后的index仅确保确定性。不使用加权和，也不假定较小位移一定较低光损耗。

对最小M_after并列候选的观察：M0009有331个，length delta全0、victim CROSS数307…311；M0001有341个，length delta全0、CROSS数102；M0023有342个，length delta约5.6…126 mm、CROSS数156…168。三组此层全部new_multi_created=0，说明本样本主要由位移打破并列。

几何长度变化已记录；known non-crossing loss、crossing angle没有纳入排名或声称已测量。CROSS次数已记录但不能充当total crossing loss，缺少完整角度损耗模型。未来可以单独对照这些secondary metrics，不在本轮给任意权重。minimum_M_after列覆盖几何有效候选；best只从所有验收条件通过的候选中选，本次两种范围的异常检查均通过。

## 13. Strict Monotonicity

只允许整数M严格下降；M相等即使旧目标消失也拒绝，M增加更拒绝。完整未来循环若每步满足此条件，从318出发至多318次成功提交，不代表必然达到0。

本次真实扫描发现目标已消失但M未下降的候选：M0009有15个，M0001有4个，M0023有2个；均不接受。四案例各自还出现18/10/1/2个M增加候选。可见“目标消失即接受”在当前真实数据中确实不成立。

严格单调与有限single-victim自由度可能停在局部最优，需要暂时持平/变差或多route协调的解会被排除。没有证据据此跳过depth-1，不实现非单调搜索、tabu、退火或depth-2。

## 14. Special-Z Policy

58条special作为固定witness/carrier保留在所有511对求交中，不能删掉它们来获得虚假的ordinary-only改善。special不占ordinary track，不参加victim排序，不生成其替代geometry。若未来目标全部不可移动，标记NO_MOVABLE_VICTIM；本baseline此类目标为0。

M0009最低并列为special101与ordinary302，尝试302；M0023最低special13被跳过，尝试ordinary318。二者都保留special原几何，并观察到strict improvement。

## 15. Representative Real Cases

事先固定每类按保存M ID取首个满足条件者，没有根据候选成功情况挑样本。

| 类别 | 目标 | Route IDs及原score | 首ordinary victim |
|---|---|---|---:|
| A：PAPER_LIKE ordinary-only | M0011 | 4:3，404:5，436:7 | 4 |
| B：上下异侧NON_PAPER_LIKE，含非邻接Arc×V | M0009 | 3:2，101(special):1，302:1 | 302 |
| C：Arc×Arc | M0001 | 0:2，300:2，345:2 | 0 |
| D：PAPER_LIKE special-carrier | M0023 | 13(special):1，182:3，318:2 | 318 |

B与D都含special，但B的上下异侧非邻接构型与D的同侧paper-like carrier不同，类别允许交叉。C三者同score且替代数相同，route_id只作最后确定性规则，不能说route0比300/345更优。

## 16. Feasibility Probe

每案例独立从未修改的318 baseline开始，仅尝试首ordinary victim，完整扫描347位置（346替代+1原位），总1388候选。没有第二victim试验，更没有全318循环。

| Case | 候选 | 几何合法 / 无新增异常 | 最小M_after | 可接受strict候选 | 最佳下降量 | 扫描秒数 |
|---|---:|---:|---:|---:|---:|---:|
| M0011 | 347 | 347 / 347 | 318 | 0 | 0 | 87.72 |
| M0009 | 347 | 347 / 347 | 317 | 331 | 1 | 85.34 |
| M0001 | 347 | 347 / 347 | 316 | 342 | 2 | 32.14 |
| M0023 | 347 | 347 / 347 | 316 | 344 | 2 | 33.49 |

**318→317 / 318→316 / 318→316均为FEASIBILITY RESULT，不能相加或写成连续恢复后的313。正式M仍为318。**

| Case | 原→最佳track | 最佳y(mm) | removed / added | length delta(mm) |
|---|---|---:|---:|---:|
| M0009 | 469→457 | 85.0 | 1 / 0 | 0 |
| M0001 | 478→452 | 84.125 | 2 / 0 | 0 |
| M0023 | 97→113 | 24.8 | 2 / 0 | 5.6 |

M0001删除(0,300,345)、(0,300,348)；M0023删除(13,182,318)、(14,182,318)；M0009仅删除其目标。以上最佳候选无新增主集multi。

四个原track回放对照均M_after=318、目标保留、added=removed=空，确认没有因保存Arc反序列化末位误差产生虚假收益。M0011仅可标记FIRST_VICTIM_EXHAUSTED；没有尝试其他victim，**不能标记SINGLE_VICTIM_UNRECOVERABLE**。

### Independent exact revalidation

单独验证入口只读取保存geometry、快照与候选track标量，不读取候选pair/adjacency cache，也不调用local_multis或evaluate。重新正式构造winner，检查自交，重算R与511条route；枚举所有C(511,2)=130,305个可能含R三元组，对于两条R边都是single CROSS者，重新求其固定第三边，而不是读取保存pair缓存。

| Winner | 重算R-star pairs | 重算固定第三边pairs | 独立M_after | 结果 |
|---|---:|---:|---:|---|
| M0009 / 302 | 511 | 37,128 | 317 | PASS |
| M0001 / 0 | 511 | 4,371 | 316 | PASS |
| M0023 / 318 | 511 | 5,995 | 316 | PASS |

所有added/removed canonical集合与delta逐项一致，目标消失、M严格下降、无新增TOUCH/OVERLAP或self异常。该独立性针对缓存与枚举路径，底层exact kernel及criterion复用工程真值层，并非另写第二套数学kernel。它独立验证了受影响全集；不含R部分依赖已保存、已验证baseline和几何不变证明。**本轮没有声称对每个winner重做全512 all-pairs。**

未来正式COMMIT之前，推荐从完整候选布局重新执行全部130,816 pair及原detector，与增量总集合比较，校验occupancy/endpoint/special/hash，再原子发布；这项重验证只对选出的winner执行，不对每个candidate执行。

## 17. Complexity Estimate

每候选pair成本为511次现有Line/Arc kernel；multi部分最坏检查C(511,2)=130,305个邻居对，实际为C(|S_R|,2)，可进一步复用固定single-cross adjacency减少枚举。本次实现为可审计的邻居两两枚举加固定pair查询，没有改kernel或空间近似。

四case合计709,268次candidate-star pair计算，扫描约238.68秒；这是本机本轮测量，不外推318全量运行时间。baseline固定pair map约49,502个非空CROSS pair；临时delta仅511个pair，保存全1388候选的评分与集合差分，不保存新的正式routing几何。

较小victim_score降低旧受影响multi数，却不会将511 pair检查数变少；不能把score当作可靠运行时预测器。

## 18. Failure / Rollback Semantics

状态规格：TARGET_MULTI → SELECT_VICTIM → TEMP_REMOVE → ENUMERATE_CANDIDATES → BUILD_EXACT_GEOMETRY → DELTA_INTERSECTION_UPDATE → DELTA_MULTI_UPDATE → SCORE_CANDIDATE → ROLLBACK_CANDIDATE。全部候选结束后SELECT_BEST → INDEPENDENT_VALIDATE → COMMIT（未来正式实现），或者下一victim / NO_RECOVERY。

无候选、非法geometry、kernel异常、目标未移除、equal-M、worse-M均丢弃私有候选。validator失败不得commit，应保留错误证据；在证据未厘清前不把实现错误当几何不可恢复。超时/取消标记INCOMPLETE，不标记全部候选耗尽。只有所有可移动victim的完整合法候选集合均失败，才能标记SINGLE_VICTIM_UNRECOVERABLE；没有可移动者另列NO_MOVABLE_VICTIM。

本沙箱不维护可变正式assignment/cache状态，全部读前后对象深拷贝相等：occupancy、waveguides、preparations、geometry、pair map、multi集合、scores。新candidate的端点也与输入隔离。143个既有src/tests/scripts/outputs/docs/config/data文件SHA256不变，两个源Excel哈希不变；证据见protected_hashes与integrity JSON。

## 19. Recommended Implementation Boundary

| 模块 | 当前可复用/后续职责 |
|---|---|
| src/router_2d.py | 复用grid、preparation、TrackAssignment、骨架生成；正式allocator本轮及建议depth-1原型均无需修改 |
| src/models.py | 复用Point/Line/Arc/SmoothedRoute；因模型可变，跨candidate需私有副本；无需更改基本模型 |
| src/geometry.py | 正式圆角构造、radius/continuity校验、解析长度直接复用 |
| src/collision.py、physical_intersections.py | exact primitive/pair、自交、physical consolidation直接复用 |
| src/multi_crossing.py | 原criterion直接复用；不得重写阈值或丢弃double |
| src/multi_crossing_delta.py | canonical triplet与集合差分思路复用；现有文件不是完整recovery事务引擎 |
| src/multi_attribution.py | 保存geometry反序列化与case身份复用 |
| src/hierarchy_diagnostic.py | 保留只读诊断；仅paper-like候选排序可选信息，不作为恢复必要条件，不计算K |
| 新独立recovery组件（未来） | 负责版本状态、single-target多victim回退、局部delta与原子事务；默认不接入allocator |

本轮新辅助实现全部位于scripts：local_recovery_feasibility.py、audit_local_recovery.py、verify_local_recovery.py、finalize_recovery_audit.py、run_local_recovery_tests.py；测试位于tests/test_local_recovery_feasibility.py。没有修改任何既有src实现。辅助入口没有正式commit功能。

可复现命令（项目根目录，既有venv，无新依赖）：

```powershell
.\.venv\Scripts\python.exe -B scripts/audit_local_recovery.py . outputs
.\.venv\Scripts\python.exe -B scripts/verify_local_recovery.py . outputs
.\.venv\Scripts\python.exe -B scripts/finalize_recovery_audit.py . outputs
.\.venv\Scripts\python.exe -B scripts/run_local_recovery_tests.py . outputs/step_8_5_m1_6_tests.json
```

上述扫描命令仅供复现记录；用户已要求本轮停止，不会再次运行或扩大。

## 20. Remaining Risks / Recovery Target Order

“先选哪个multi”与“该multi里先动谁”是独立政策：

| 目标顺序 | 优点 | 限制 |
|---|---|---|
| A：canonical multi ID | 可复现、成本小、实验可解释 | 不优先热点或可恢复性 |
| B：含当前最高multi-count route优先 | 优先关注高依赖区域 | 不代表应移动最高score成员，也可能更难 |
| C：最容易恢复优先 | 已有有效probe证据时可快速取得改进 | 预先评估成本高，commit后证据失效，不能凭标签猜容易 |
| D：空间hotspot | 便于定位和展示局部聚集 | 相近重心不代表pair依赖局部，存在跨侧长carrier |

推荐下一受控depth-1步骤先采用A，便于独立验收和定位问题；B/C/D仅保留未来可对照策略。任何顺序下victim内部仍按最低multi_count优先，不混同两个层次。

四个按构型选出的case不是随机样本；3/4首victim成功不能当作318总体成功率。未比较第二/第三victim、随机顺序或最高score优先；**不能证明lowest-multi-count victim ordering最优，也不能证明其优于其他顺序。** 本轮证明的是实现可行且真实数据上存在单根ordinary的strict-improvement候选。

特殊carrier固定可能留下不可恢复目标，exclusive也可能限制局部最优；现有主集criterion不代表全部制造安全或total optical loss。smallest-score以旧依赖少为动机，有数据上的描述性合理性，无最优性或全局消零保证。

## 21. Verdict / Tests

**M1.6 PASS（design + sandbox feasibility）。** 当前数据结构足以实现single-victim exact recovery；local delta可安全定义；copy-on-write rollback可避免污染；special可完整隔离且仍作为witness参加求交。

首次新增18项测试，加历史487项，**505/505 PASS**。随后仅补充非法track index（负值、越界、bool）拒绝测试与输入防御，最终新增19项，**506/506 PASS，失败0**。不是将历史505冒充最终计数。

覆盖unique victim_score、score主排序、tie保留/稳定顺序、special排除、临时释放与错误不污染、candidate端点深隔离、local pair delta、不受影响输入保持、独立全检测微型fixture对比、single/double/TOUCH multiplicity语义、M_after差分、目标保留拒绝、equal-M/worse-M拒绝、稳定candidate ranking、正常/异常rollback、非法index。四真实case另外有完整状态对象相等、原位negative control、954行交点一致、winner独立exact复核及文件哈希检查。

## 22. Recommended Next Step

建议 **Step 8.5-M1.7：受控 single-target depth-1 recovery 原型与事务验收**，以本次证据为起点，明确single-target、逐ordinary victim回退、所有候选评分、独立全布局winner验证、完整rollback/version失效语义。仍以独立沙箱/显式实验开关为边界，先不建立318目标迭代循环、不更换正式baseline。

值得先做depth-1：三种真实构型已有独立验证的strict improvement，尚无证据需要直接depth-2。M0011的第一victim失败正好说明后续应验证single-target内的下一ordinary回退，不能跳成多根同时rip-up。

**此处仅给下一步建议。本Step完成并停止；无正式allocator修改、无recovery commit、无迭代reroute、无新增案例。**
