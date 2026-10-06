# Step 8.5-M：Hierarchy / Fragment Compatibility & Exact Rule Derivation

审计日期：2026-09-11。结论：**审计完成，但存在关键歧义，尚不具备直接忠实实现论文 allocator 的条件。**

## 1. Scope 与证据分级

本轮仅核读论文、检查当前实现与历史证据、推导规则并设计后续小实验。仅新增本报告；不改 router、模型、geometry、判据、配置、原始数据或既有结果，不运行新 routing、collision、loss 或全量 G1。

- **PAPER FACT**：原文明确文字、公式或图表；不等于前代源码已验证。
- **CODE FACT**：当前源码直接可见，或明确注明来源的既有工程审计结果。
- **PROJECT-SPECIFIC**：本报告为当前工程提出的数学解释、数据结构或实验规则，不是论文原方法，也未实现。
- **AMBIGUOUS**：证据不足、符号/统计冲突，或无法忠实恢复的实现细节。

正式 baseline 保持 ascending、exclusive A、guard OFF、r=5 mm、width=0.05 mm、spacing=0.125 mm、pitch=0.175 mm。本报告中的 hierarchy 是二维 strip 约束，与模型 Layer 的物理 Z 层无关。

## 2. Paper Evidence 与代码来源

### 2.1 一手论文

**T：本科论文**《面向板级高速光互连应用的光波导智能排布技术研究》，黄志杰：
[C:/Users/lihao/Desktop/Graduation Project/黄志杰_毕设论文.pdf](<C:/Users/lihao/Desktop/Graduation Project/黄志杰_毕设论文.pdf>)。

本报告 T 的页码采用页脚正文编号；相关 PDF 物理页=正文页+5。由于文本提取字体映射异常，关键公式、参数、类别及实验表述均以渲染页面目视核对为准。

**I：IEEE 短文** Automatic high-density polymer waveguide layout for on-board high-speed optical interconnect，Zhijie Huang 等，©2020 IEEE：
[C:/Users/lihao/Desktop/上海交通大学/文献/黄志杰.pdf](<C:/Users/lihao/Desktop/上海交通大学/文献/黄志杰.pdf>)。

用户本轮补充了 I 的路径，已直接核读全部三页；不再依赖先前摘录。I 页码为 PDF 第1—3页。不进行网络补全或 EXE 逆向。

| 证据位置 | 支持内容 |
|---|---|
| T 正文10页，3.1.1、3.1.3 | 式3-1、w/d、strip底边坐标、按连接关系排序端口 |
| T 正文11—12页，3.1.3—3.1.5 | 式3-4—6、四类x顺序/y扫描、区域划分、非90°Z几何 |
| T 正文14页，3.2.1 | 三交点三角形、至少两条短边的 multi 定义及终止端构图前提 |
| T 正文15页，3.2.1—3.2.2 | 式3-10—14、K与终止端弯曲检查 |
| T 正文16页，3.2.3.1 | 动态D与式3-15、待完成横向布线的相邻PMT端点 |
| T 正文17页，3.2.3.2 | 两个端点列表、三项检测、类别结束后的区域封锁 |
| T 正文22—23页，4.1 | 512、150×150、r=5、PMT间距1.7 mm、部分错位与人工调整连接图、100%及821/857条带 |
| T 正文25—27页，4.3—4.4 | 半径对比、150×200对照、fragment-only与联合优化统计 |
| T 正文28页，全文总结 | 高密度上下来源波导重叠及最小间距仍存在局限 |
| I 第1页 Table I | width/height=50 μm，表头 Pitch=125 μm；光学参数 |
| I 第2页 Fig.1与正文 | 端口分配顺序、初始Δy为一个pitch、overlap/multi反馈、增大间隔或减小r |
| I 第3页、Fig.6 | r=5仍有少量multi；r=4无multi；平均损耗5.61/9.90 dB |

### 2.2 当前工程证据

直接检查 src/models.py、src/router_2d.py；对照以下既有报告，不把历史测量冒充本轮重跑：

- docs/reports/step_8_5_legacy_optimization_compatibility_audit.md（Step K）。
- docs/reports/step_8_legacy_512_snapshot.md。
- docs/reports/step_8_5_exact_multi_guard_ab_v01.md 的 Step L 最终审计。
- outputs/step_8_5_exact_multi_guard_exhaustion_summary.json 及其既有 witness 审计证据链。

本轮新证据对 Step K 的补充：**T 4.1直接明确实验PMT间距1.7 mm**，不再仅依赖4.5−16×0.175反推；但它与实际纵向波导间距的区别仍未消失。I 明确初始Δy为一个pitch，但没有明确每次失败后增加间隔的离散量。保留旧报告，不改写历史记录。

## 3. Baseline K Reconstruction

### 3.1 符号与实体

**PAPER FACT**，T 正文10、14—16页。长度须统一单位；下表用 mm 对当前参数换算，K 无量纲。

| 符号 | 论文定义/几何实体 | 出现位置 | 单位及限制 |
|---|---|---|---|
| w | 波导宽度 | 3-1、3-4—5 | 长度，0.05 mm |
| d | 波导间距；也用作交点聚集距离阈值及K除数 | 3-1、3-10—15 | 长度；原始声明0.125 mm，K步长语义有歧义 |
| D | 基础PMT间距；优化段落解释为相邻PMT纵向直波导间距 | 3-5、3-10—14 | 长度；布局间隔与实际x差需区分 |
| Dh | 两条横向直波导之间的距离 | 3-10—12 | 长度；几何y偏移，不是strip数量 |
| r | 弯曲半径 | 3-10—15 | 长度；本次保持5 mm |
| gap | 构图中两个交点的距离 | 3-10 | 长度；不是有限宽度波导边缘净距 |
| K | 候选前面需检查的strip数量 | 3-14—15 | 无量纲；公式通常返回非整数 |
| xt | 当前波导终止端x | 3-15 | 长度坐标；取算法终止端 |
| xa | 相邻PMT中尚未横向布线的最近波导x | 3-15 | 长度坐标；不等于PMT ID或local_id |

### 3.2 逐式复原

**PAPER FACT**，按 T 正文15—16页转录：

```text
(3-10) gap = D - [r - sqrt(r² - (r-Dh)²)] >= d
(3-11) 0 >= Dh² - 2rDh + (r+d-D)²
(3-12) Dh >= r - sqrt(r² - (r+d-D)²)
(3-13) r < D + sqrt(2d(D-d))
(3-14) K = [r - sqrt(r² - (r+d-D)²)] / d
(3-15) K = [r - sqrt(r² - (r+d-|xt-xa|)²)] / d
```

令 L(D,d,r)=r−sqrt(r²−(r+d−D)²)，仅作为本报告数学简写，不新增工程配置。

**PAPER FACT**：3.2.1的论证依赖旧排序产生的规则几何：两条横向波导与相邻PMT的纵向/弯曲部分相交，三个交点可能聚集在终止端附近。Dh较小且终止弯曲伸入相邻PMT区域时，gap可能小于d；若三交点三角形至少两边小于d，则构成论文定义的multi。增加横向段分离可使该局部构图中的gap满足要求。

**PAPER FACT**：3.2.2先找到基本可用strip，再回看先前遍历的K个strip，检查其中波导是否与当前终止端弯曲相交；若相交则当前候选不可用，继续扫描，否则放置并标记。不是把前K条waveguide直接判为冲突，也不是无条件空出K条track。

**PROJECT-SPECIFIC 数学解释**：3-10中圆弧相对纵向线的横向突出量是方括号项，D扣除该突出量得到gap。解出满足gap阈值的Dh下界L，便得到一个局部危险距离带；K试图把该连续距离带转成需要回看的strip跨度。这是旧排序/终止端构图下的预测，并非任意Line/Arc布局无multi的完整证明。

### 3.3 适用域不能省略

**PROJECT-SPECIFIC 数学审计**：

1. 3-10根号要求0≤Dh≤2r；90°弧的实际构图还要求选择相应弧段，不能只看根号有实数。
2. 移项得到 sqrt(r²−(r−Dh)²)≥r+d−D。右侧若为负，平方不再是等价变换；此时不可机械沿用3-11。
3. 3-12使用二次解的小根。若在0≤Dh≤r的相关分支，且d≤D≤r+d，L才可按该分支解释，并随D增加而不增。
4. D<d时该分支无满足阈值的解；D≥r+d时原根号下界非正，不能把L在此后的反向变化当成“D越大K反而增加”的物理规则。
5. 3-13是原文给出的半径条件，不是当前精确detector的充分必要条件。其严格不等号与前式非严格边界也需要实现约定。

**AMBIGUOUS**：论文未将分支、域外值、边界等号及数值容差写成程序规范。本报告不选择clamp、K=0、报错或fallback。

## 4. d / pitch 与基础 D

### 4.1 d 逐处审计

| 位置 | PAPER FACT | 工程解释与歧义 |
|---|---|---|
| 3-1 | (w+d)Ny=Ha，d称波导间距，取125 μm | d最可信对应spacing，strip重复步长是175 μm |
| 3-4、3-5 | 端点x增量w+d | 同样支持d为宽度之外的间隔 |
| 3-10 | gap≥d | 以交点距离与d比较；没有写有限宽度修正 |
| 3-11、3-12 | 由3-10沿用同一d | 未见重新定义为pitch |
| 3-13 | 沿用d给出半径限制 | 未见独立新定义 |
| 3-14 | L/d被称为strip回溯数量 | 与3-1 strip宽w+d不一致，关键歧义 |
| 3-15 | 动态D替换后仍除d | 延续3-14的步长歧义 |
| I Table I与Δy | 表格直接写Pitch=125 μm，Δy初始为一个pitch | 不能用I表格替换T的w+d=175 μm，也不能断言两篇数值口径完全相同 |

**结论：PAPER FACT + AMBIGUOUS**。T原始符号最可信读法是d=0.125 mm spacing，未找到3.2把d明确改称0.175 mm pitch的证据。但公式K以d计strip与前文划分不一致，无法确认是忽略宽度近似、符号重用还是笔误。

**PROJECT-SPECIFIC**：若以后映射当前工程，必须分开保存“距离阈值s=0.125”和“网格步长p=0.175”。把物理距离L换成当前track跨度的连续量应为L/p；这属于工程换算，不得标为论文原式K=L/d。本轮不改任何阈值或K实现。

### 4.2 D候选工程量

**PAPER FACT**：T 4.1正文22页明确实验PMT间距取1.7 mm；T 3.2.3.1又解释，相关D其实取决于相邻PMT纵向波导之间的距离，固定PMT间距是保守临界取值。因此“论文用过1.7”已确认，“当前每个candidate实际D都等于1.7”不成立。

下列快照尺寸来自既有Step K测量，未重跑布局。

| 候选量 | 物理含义 | 是否等价基础/动态D | 结论 |
|---|---|---|---|
| 1.7 mm | T 4.1的PMT布局间隔；也满足4.5−16×0.175 | 对应论文实验布局参数；不自动等于最近纵向中心线距离 | 布局值已确认；不可无条件代入动态式 |
| 1.875 mm | 同侧相邻PMT最近两个实际端点x差 | 是实际最近纵向中心线候选距离；不筛待布线集合 | 可测，但未证明就是每一步动态D |
| abs(xt−xa) | 特定时刻、特定邻接PMT的最近待布线端点距离 | 与3-15文字最直接对应 | 需先明确方向、状态与特殊路径政策 |
| 4.5 mm | 同侧相邻PMT最左端点x的增量 | 不是PMT间隙或最近波导间距 | 不可代入 |
| 2.8 mm | T的W=16(w+d) | PMT布局占用宽度 | 不是D |
| 2.625 mm | 16个端点中心首末跨度=15p | 中心坐标跨度 | 不是D，也不等于W |
| 1.825 mm | 1.875−0.05得到的最近波导边缘净距 | 人为按有限宽度算出的量 | PROJECT-SPECIFIC；不是已确认D |
| PMT中心/壳体边界间距 | 模型未提供相应几何实体 | 无从直接测量 | AMBIGUOUS，不伪造 |

## 5. K Discretization Ambiguity

**PAPER FACT / AMBIGUOUS**：论文未规定floor、ceil、round或int；示意图回看两条不能证明取整规则。也未精确定义窗口是否含候选自身、边界等号、空strip或跨类别条带。

**PROJECT-SPECIFIC 数学推导**：必须先区分“最小允许间隔”与“要检查的近邻集合”。

- 若要求离散分离n·p≥L，则最小整数n=ceil(L/p)。floor会在L/p非整数时低估要求。例如L/p=2.3，2p<L，3p≥L。
- 若要枚举满足j·p<L的先前strip，j为正整数，最后一个风险索引是ceil(L/p)−1；L/p=2.3时只需j=1,2，floor=2恰好覆盖这个集合。
- 若定义为j·p≤L，则最后索引是floor(L/p)。L/p=2时严格窗口只到1，包含边界的窗口到2。
- 因此“floor必然不安全、ceil必然正确”不成立。ceil作为窗口大小可能多查一条；若多查后硬拒绝，可能额外损害布通率。
- 以d代替p、计算L的阈值错误、漏掉真正几何实体或使用错误扫描方向，均不能靠ceil修复。

本轮不选择取整方案。未来必须先确定窗口谓词，再按整数索引实际y差验证，不能先决定int(K)再倒推语义。

## 6. Hierarchy Optimization 与 Dynamic D Mapping

### 6.1 原论文含义

**PAPER FACT**，T 3.2.3.1：固定D取PMT间距会扩大K、浪费空间。在纵向端点已排好后，检查邻接PMT尚未安排横向段的波导，找与当前终止端最近的一根，用abs(xt−xa)替代固定D。若有效分支上实际距离更大，则L/K可缩小，从而释放部分原来过度限制的候选。

不是改变PMT物理布局，不是重新分配local_id，也不是把已经commit的最近波导当xa。

### 6.2 当前数据是否够用

| 当前实体 | CODE FACT | 缺少的工程定义 |
|---|---|---|
| Port.position | 可保存Point2D；当前512快照有实际x/y | None/3D应诊断为不适用，不能补坐标 |
| Port.pmt_id、PMT.ports | 可按PMT聚合端点 | 无几何邻接字段；不允许ID±1 |
| Port.local_id | 可为None；快照保留None | x排序可计算距离，但不能冒充前代槽位号 |
| Waveguide.id | 同一PMT pair仍保留独立需求 | 端点候选必须保留port_id和route_id，不能按pair去重 |
| _algorithmic_endpoints | U取较小x作为a；否则按(pmt_id,id)元组取a | b是当前算法终止端，不证明与论文终止端一致 |
| RoutePreparation | 类型、侧别 | 不含完整邻接/时序 |
| TrackAssignment / 已commit集合 | 可表达哪些ordinary已成功提交 | 最终结果不能直接代表早先candidate时刻的pending集合 |
| SmoothedRoute2D | 独立Line/Arc几何 | 本身不保存邻接PMT和端口分配状态，需通过ID关联 |

**PROJECT-SPECIFIC 最小诊断规格，不实施**：

1. 只读取已有Point2D端点；按y侧别分组，再按同PMT端点x范围排序PMT。左右邻接是几何相邻，不用PMT编号。
2. 对明确给定的commit前缀，取得当前工程算法终止端xt。
3. 分别列出终止PMT左邻、右邻的端点，保留route_id、port_id、x和状态；不提前挑“危险侧”。
4. 对每一邻居的明确pending集合求argmin abs(xt−x)，输出全部并列候选与距离。
5. 输出NO_ADJACENT、NO_PENDING、UNCONFIRMED_DIRECTION、UNSUPPORTED_GEOMETRY等诊断状态，不把空集变成D=0、D=∞或K=0。
6. 当前route自身、失败但未commit的route、尚未遍历ordinary、独立special必须分栏；不得把一次失败当作已完成横向布线。
7. 仅在公式参数及适用域明确后可输出连续L与L/d、L/p对照；不输出用于allocator硬拒绝的整数K。

### 6.3 十二项边界逐项审计

| 情况 | 论文支持 | 当前工程需定义 / 结论 |
|---|---|---|
| 1. 顶部PMT左/右邻接 | 使用邻接PMT及终止端 | PROJECT-SPECIFIC：按同侧x顺序给出两邻；终止弯曲应检查哪侧未明确，不能默认右邻 |
| 2. 底部PMT邻接 | 正文称对应处理/对称性 | y反射不改变左右x顺序；危险侧仍需按弯曲方向核对，不照搬顶部公式分支 |
| 3. 最左PMT | 没有完整边缘伪代码 | 左邻不存在但右邻可能存在；不能取消全部层级检查 |
| 4. 最右PMT | 同上 | 右邻不存在但左邻可能存在；同理 |
| 5. 邻接PMT不存在 | 未规定返回值 | NO_ADJACENT；不自动等于全局无multi风险 |
| 6. 邻接存在但相关波导全完成 | 原文只选未完成横向者 | 空pending集合的K政策未规定；已commit几何仍需独立验证 |
| 7. 有邻接但无候选危险波导 | 未给完整危险候选过滤器 | “没有pending”与“有pending但几何不危险”必须区分；缺少可证明过滤规则时标未确认 |
| 8. top-U | 第一类U、终止端构图最接近 | 当前U按x定向，但论文排序/端口分配前提仍需核对；不直接宣布可忠实映射 |
| 9. bottom-U | 第二类U，反向y扫描 | 检查方向反转、弧分支需反射，不能复用固定i+K |
| 10. top→bottom Z | 第三类、正文为x降序/y升序 | 当前算法类别按ID视图确定，且当前y降序；明显不等同论文前提 |
| 11. bottom→top Z | 第四类、x降序/y降序 | y方向相近但当前x升序；终止侧为顶部，需独立核对邻接侧 |
| 12. special-Z | 有非90°弯曲描述，部分不再有横向直段 | 当前58条独立几何没有普通track提交语义；不能把其直接当普通pending或套90°K |

**AMBIGUOUS**：四类ordinary的算法方向与论文是否一致、危险邻接方向、特殊路径是否参与pending、失败route的未来状态，均不足以恢复前代时序。本轮不建立状态机或新增模型。

## 7. Hierarchy 与 Exact Detector

**CODE FACT**：现有exact pipeline按真实Line/Arc求交、physical consolidation后分类multi。Step L已独立验证明确witness。它是现有工程判据的依据，不是有限宽度、全部touch/overlap、所有制造约束的认证。

| 方案 | 正确性 | 保守性 | 运行成本 | 论文一致程度 | 布通率风险 |
|---|---|---|---|---|---|
| H1 只用hierarchy K | 只在论文构图/排序前提下具有预测依据；不能证明当前全局无multi | 参数/取整/邻接不当可过度拒绝，也可漏检 | 邻居索引和局部窗口通常低于全候选exact，但未测量 | 补齐前提后较接近论文；当前直接套公式不忠实 | 可能释放固定D约束，但不能保证完成 |
| H2 hierarchy K + exact candidate确认 | exact覆盖全部相关已commit路径及正确事务时可确认新增candidate是否引入目标multi；仍须最终独立验证 | K硬拒绝可能拒掉本来exact安全的候选；exact不能恢复已被剪掉的机会 | 多一层K且仍需exact，是否更快取决于剪枝收益，不能预报倍数 | 属论文预测加现代验证的PROJECT-SPECIFIC混合 | Step L式贪心耗尽仍可能出现；hierarchy不是自动补救 |
| H3 hierarchy仅改变候选优先级 | 本身不保证无multi；独立final validator负责暴露残留 | 不以K缩减候选集合，预测误差不会直接删除候选 | 排序较轻，最终exact另计；若同时逐候选guard则变成混合方案 | 是工程启发式，不是论文原硬检查 | 避免K直接造成耗尽；exclusive/顺序等限制仍在 |

**PROJECT-SPECIFIC 推荐架构分析**：保持几何真值层独立，把K称为spacing policy或candidate heuristic；未经证明不称“安全剪枝”。先比较K建议与exact标签差异，再决定是否允许硬拒绝。最终验证应包含ordinary和独立special的完整geometry，并保持现行multi判据，不把K通过当exact通过。本轮不运行该验证或修改guard。

## 8. Fragmented Area Optimization

### 8.1 论文原始流程

**PAPER FACT**，T 3.2.3.2：

原strip只有y属性；放入一条波导就整体不可用，剩余横向空白成为阶梯状碎片。增加左右端点列表后，通过端点编号比较判断新横向范围与已有范围是否重叠；不重叠的波导可复用同strip。

需忠实记录原文列表命名：**右端点列表记录波导起始编号，左端点列表记录终止编号**。不能因直觉交换字段后称为逐字复现。编号与x排序的对应方向要结合旧端口分配和类别确认。

### 8.2 三项检测与时序

| 检测 | PAPER FACT：原因 | 当前工程映射 |
|---|---|---|
| 当前strip内overlap | 避免复用横向范围重叠 | 候选interval与该track所有已占用interval比较 |
| 先前遍历K strips | 避免当前终止弯曲附近multi | 按当前扫描方向回看，窗口还依赖K离散语义 |
| 尚未遍历方向的相关区域 | 复用后不再单调阶梯，当前候选另一侧可能已有同类路径 | 需检查future方向已有几何；原文只称若干块，不明确必为同一个K |

**PAPER FACT**：三项均通过才插入。第三项不是检查“未来尚未生成的所有路径”，而是当前扫描未到的区域可能已被先处理的waveguide占用。

**PROJECT-SPECIFIC**：未来事务必须在所有所需检查完成后才写入occupancy，拒绝不得留下区间/geometry/cache。此为可测试工程规格，不是已查到的旧代码实现。

## 9. Compatibility with Exclusive Track 与类别区域

### 9.1 最小数据变化

**CODE FACT**：当前实际occupancy是list[int | None]，存route_id或None，不是字面bool，但语义确实是occupied/free。每track至多一个ordinary。

**结论**：fragment复用**明确破坏exclusive A**；不能作为当前baseline的不改变行为小修补。

**PROJECT-SPECIFIC 仅设计**：未来可用track_index → list[(xmin,xmax,route_id)]，端点规范化并保留route_id；如需区域锁定，另有每track或每区域禁用标记，不能把空interval表等同永远可用。无需改变Port/Route基础模型。

必须先定义interval是骨架端点范围，还是圆角后的真实水平直段范围；二者不相同。论文编号列表更接近端点/纵向位置决定的范围，但源码未确认。排序、相等边界、touch政策、零长度和special无水平段都要独立规定。

### 9.2 排序与扫描不能混为一谈

**CODE FACT / PAPER FACT**：下表i随y递增；“当前ascending”是route主排序，不是所有类别都向上扫描。

| 类别 | 论文起始x排序 | 论文y扫描 | 当前默认x排序 / y扫描 | 当前先前strip方向 / future方向 |
|---|---|---|---|---|
| top-U | 升序 | 降序 | 升序 / 降序 | i+1… / i−1… |
| bottom-U | 升序 | 升序 | 升序 / 升序 | i−1… / i+1… |
| top→bottom Z | 降序 | 升序 | 升序 / 降序 | i+1… / i−1…；与论文不同 |
| bottom→top Z | 降序 | 降序 | 升序 / 降序 | i+1… / i−1… |

T 3.1.4还讨论U反向排序可能有类似效果，但不能据此证明当前descending variant等于旧完整allocator。只改变top-U排序未修复Z排序、端口编号语义或区域封锁。

### 9.3 区域封锁

**PAPER FACT**：T正文11页第一类U完成后，以该类最小横向y为分界，其上strip对其余类别不可用；正文12页说明第二/第三类自底部向上形成分区，第四类最后在第一类之下，四类形成分开的区域。

**PAPER FACT**：fragment段落又要求第一类U完成后把其布线区域全部封锁，并对第二类U、第三类Z完成后的区域作类似处理，避免类别间区域重叠。

**AMBIGUOUS**：fragment复用后区域是否按极值包络取整、边界strip归属、第二/第三类封锁具体时点与精确集合未写成伪代码。不得把“已占用track”当成“整个类别区域”，也不能自行只锁那些非空条带。

**CODE FACT**：当前没有这些类别区域锁；四类标签表面对应，但Z方向由算法端点视图决定，special另走独立几何。T 3.1.5的Z几何描述还涉及不足2r而无水平段的结构；不能把论文第三类Z整体等同当前58条special，或把special强行当第五个论文封锁区域。

## 10. Compatibility with Exact Geometry

### 10.1 区间条件的必要/充分性

**PROJECT-SPECIFIC 几何分析**：

- 若interval指同y真实水平直段，则正长度重叠会造成这两段overlap。因此“不发生正长度水平重叠”是避免该类overlap的必要条件，但远不足以证明整条路径安全。
- 若要求闭区间完全不相交，还排除了端点touch；是否必要取决于现行touch是否允许，不能无说明把接触当multi。
- 不含水平段的special不能用空interval推断无风险。
- 对现有multi判据本身，interval条件不是充分必要条件：它没有检查三条路径的三个实际交点；某些overlap/touch也未必满足当前multi分类前提。
- 若interval改成整条路径完整x投影，且两路径严格分离，则可证明这两条路径彼此不相交。但不能由此保证它们各自与其他track、special或其他路径组没有multi。较大的投影区间也可能过度拒绝实际不相交路径。

因此，论文fragment条件在当前系统中应视为**复用候选的局部几何约束/heuristic**，不是全局exact-safe证书。也不能反过来断言任何完整x投影不重叠的两条普通路径仍必然可能彼此相交。

### 10.2 一个不运行实验的解析反例

**PROJECT-SPECIFIC 数学例子，非真实512结果**：

两条top-U，r=5，track y=10，端点分别为A:(0,150)→(20,150)，B:(18,150)→(38,150)。

圆角后水平直段x区间分别为[5,15]、[23,33]，不重叠。但A右弧圆心(15,15)、B左弧圆心(23,15)，半径均5；两条相关下半四分之一弧在(19,12)相交。可直接代入两圆方程验证：4²+(-3)²=25，且点位于两条实际弧的角度范围内。

其骨架全横向范围[0,20]与[18,38]重叠，若按此范围检查会拒绝。这说明不能把论文端点列表偷偷替换成圆角后短直段interval。本例只证明arc crossing可能，不声称两条路径即可构成三波导multi。

### 10.3 exact接入边界

**PROJECT-SPECIFIC**：未来可依次做便宜的interval候选检查、已明确的K/区域规则、exact局部确认，最后独立全局validation。但：

1. 便宜检查的硬拒绝必须明确是布局policy，而非未经证明的“几何必不安全”。
2. candidate确认要覆盖相关已commit几何；只查同track会漏掉其他track、纵向段和special。
3. exact multi通过不等于无touch、overlap或满足有限宽度spacing；本轮不扩大验收判据。
4. final validator应独立从最终Line/Arc重建，不信任K或guard缓存自证。
5. H2若仍greedy/no-reroute，可能正确拒绝全部候选而无法布通；不能承诺hierarchy会消除Step L失败。

## 11. Paper Experiments 与当前项目比较

### 11.1 本科论文原文数字，保留口径差异

**PAPER FACT**，T 4.1、4.4。所有loss均是论文估算，非当前项目输出。

| 实验 | 板尺寸 / r | 布通结论 | 空间/条带原文数据 | mean / max loss |
|---|---|---|---|---|
| 512朴素，目标板 | 150×150 mm / 5 mm | 不能达到100% | 因此4.4扩大板比较 | 不填完整布局指标 |
| 512朴素，对照板 | 150×200 mm / 5 mm | 4.4给出512排布结果 | η≈0.16、ρ≈0.57；后文1128条、约99% | 5.7 / 6.9 dB |
| 512 fragment-only，对照板 | 150×200 mm / 5 mm | 给出512排布结果 | η≈0.15、ρ≈0.54；1082条、约95%；原文空间压缩至96% | 5.7 / 6.9 dB |
| 512 hierarchy+fragment | 150×150 mm / 5 mm | 4.1明确100% | η≈0.16、ρ≈0.57；4.1总857条，含边界不可用带的占用计数821、约96% | 正文5.5 / 6.6 dB；Fig.4-4 mean=5.55 |

**AMBIGUOUS / 原文统计异常**，T正文27页：

- 前页4.4及Fig.4-7/8的y轴均明确150×200；后文却写“150×150”可划分1142条。按0.175，1142与200 mm高度相符，不与150相符。可指出疑似笔误，不能悄悄改成已确认事实。
- 原文1128−1082却写减少46条；实际算术差为46，比例1082/1128≈95.92%，与“96%”一致。
- 原文联合优化使用857条，较1082少225条，约79%；但4.1把857定义为总划分数、821为包含边界禁带的使用计数。不能把857与821当成同一“实际占用数”。
- 因而可引用原文“fragment将所需最小空间压缩到96%，在此基础上hierarchy再至79%”，但必须附上述计数/板尺寸口径限制，不能作为当前算法保证或严格同板消融结果。
- 4.1/4.4的η、ρ不是布通率，也不是1−条带使用率；不能把百分比与之互换。

**PAPER FACT**：4.1为512配置32+32个PMT、每PMT16端点，W=16(w+d)=2.8 mm、D=1.7 mm。因为完整错位受板宽限制，采用部分错位，并人工调整连接关系以避免重叠。未证明用户现存Excel与论文图中每一条连接完全一致。

**PAPER FACT**：总结正文28页仍指出非常高密度时上下来源纵向波导可能重叠、最小间距不能很好保证；小交角损耗估计也有局限。因此论文“100%布通”不能扩展为当前全部制造约束或exact统计均为零。

### 11.2 IEEE与本科论文分开归属

| 内容 | IEEE短文 I | 本科论文 T |
|---|---|---|
| 512 / 150×150 | 明确；Fig.3是r=4 | 明确，4.1重点r=5联合优化 |
| increase Δy / reduce radius | 明确；初始Δy为一个pitch，失败增量具体多少未明确 | 进一步给出固定r下空间约束与优化 |
| overlap / multi反馈 | Fig.1明确高层循环 | 给局部multi定义与K检查 |
| K、动态D、hierarchy、fragment | 未公开这些公式/细节 | 第3章明确 |
| r=5是否无multi | 第3页明确仍有少量multi；r=4没有 | 优化目标和100%实验不能代替当前exact全局零multi验证 |
| mean loss r=4 / r=5 | 9.90 / 5.61 dB | 图4-4为9.85 / 5.55，正文约9.8 / 5.5 |
| max loss r=5 | 未找到明确最大值数字，不从图估读补齐 | 6.6 dB |
| fragment-only空间变化 | 未提供 | 4.4有上述不同板尺寸对照 |

**AMBIGUOUS**：I的Pitch=125 μm与T的w+d=175 μm不能自动统一；不同loss均值不能混写为同一次实验。IEEE第2页p1…pw是从左到右的概念端口编号，图内端口标注目标PMT；不能据此把快照index1/index2或PMT ID当local_id。

### 11.3 Step L为何失败而论文能报告100%

**CODE FACT，引用已完成Step L，未重算**：

21条真实exhaustion（14 top-U、7算法top→bottom Z），对应14,384次拒绝全部有独立witness验证；不是timeout误计。运行在217条partial committed时中止，不能将此当最终布通率。route451在44条已commit后，对全部756个空闲track均有真实拒绝理由。Step L最终420/420测试通过是历史记录，本轮没有重新执行测试。

| 差异因素 | 证据及解释 | 不能推出的结论 |
|---|---|---|
| exclusive比fragment严格 | 当前每track最多一路；论文允许区间复用 | 加fragment不一定解决451：它连所有空闲track都已拒绝，需改变之前的布局历史才可能不同 |
| hierarchy减小过保守K | 论文相对固定D优化 | 当前guard原本没有固定D/K，不能说去掉过大K就能直接解决当前拒绝 |
| 排序/扫描/类别锁不同 | 表9.2与源码直接支持 | 不能归因于单一ascending或descending |
| 端口分配与连接图 | 论文先按目标排序端点，并说明人工调整连接图；当前使用既有固定快照 | 尚未证明输入图、方向、端点时序完全相同 |
| 布局原点、边界及条带 | 当前800可用中心线，论文strip底边标识及含禁带统计 | 不能把857−800直接叫“可用空间损失” |
| exact判据范围 | 当前对真实Line/Arc按既定三对单CROSS条件分类；论文K依赖规则构图 | exact不必处处比K更保守；K可能误拒，exact也只证明其既定目标 |
| IEEE r5有少量multi | I明文 | 不存在“IEEE r5已证明零multi且100%”这个对照前提 |
| greedy/no-reroute | 当前拒绝不移动已commit路径 | 不证明所有512无multi方案都不可行 |

**分析结论**：Step L证实的是当前具体组合的贪心候选耗尽，不是问题全局无解。论文成功采用不同空间复用/约束/输入与时序，不能拿最终100%否定本次独立witness，也不能承诺加入某一项就恢复100%。

## 12. Candidate Engineering Routes

以下全部为 **PROJECT-SPECIFIC 方案设计，未实现**。

| 项目 | Route A：Hierarchy only | Route B：Hierarchy+Fragment | Route C：Hierarchy/Fragment+Exact Geometry Validation |
|---|---|---|---|
| 数据结构 | 邻接端点索引、pending/commit状态、D诊断；保留独占表 | A加每track区间列表、类别区域锁 | B加解析geometry关联及独立验证结果；可复用已有exact层 |
| allocator变化 | 候选优先级或明确K政策，需独立选择 | 区间复用、三项检测、区域封锁、提交事务 | B加局部确认（可选）及独立final验证 |
| 是否破坏exclusive A | 不必破坏 | 是 | 启用fragment则是 |
| paper-consistent | 部分；未复现fragment及其他前提 | 比A更接近完整论文思想，细节仍需工程约定 | 论文思想+工程验证，不能称逐行复现 |
| 实现风险 | 中：动态邻接/状态、K域和离散语义 | 高：区间实体、反向检查、类别边界、多路径事务 | 高：B的风险加候选成本及validator覆盖 |
| 预期布通率 | 可能降低固定K方案保守性；对当前无K baseline不能承诺增益 | 复用扩展容量，但其他检查可抵消，不保证100% | final-only可揭示问题；hard candidate版本仍可能耗尽 |
| 预期multi | K预测，需exact度量；不保证为零 | 同上，复用产生新相邻关系，可能降低也可能增加 | 对验收判据可给独立证据；若失败只能报告，不自动修复 |
| 测试难度 | 中：12边界、时序、阈值/步长 | 高：多区间、双方向、锁区、回滚 | 高：再加cross/touch/overlap及special覆盖、拒绝正确性 |

独立最终validation与逐候选hard guard是两种不同接入方式，必须分开实验。不得把Route C写成“必然兼得100%与零multi”的保证。

## 13. Recommended Next Step 与实验设计

**建议 M1：只读 Dynamic-D / Hierarchy diagnostic minimal prototype。不是正式hierarchy allocator。**

理由：端点坐标已存在，动态D有T 3-15直接依据；先查清邻接与时间状态，改动比fragment小；不破坏exclusive、不重新分配端口，也不必先决定K整数化。M2 fragment occupancy可作为随后独立小模型，但其区间实体、区域锁和双向检查需要更多约定。

### 13.1 M1预期输入/输出（未来任务，本轮不创建）

- 输入：固定少量Point2D微型fixture及显式commit集合；可选读取既有真实快照/保存前缀，不启动allocator或重放全量G1。
- 输出：route_id、算法终止端ID/xt、终止侧、左右邻PMT ID、pending端点列表、nearest候选及并列、各D值、边界状态。
- 若计算公式，仅作为诊断同时列L、L/d、L/p和域状态；不输出可直接驱动hard reject的K。
- 不将x排序序号写回local_id，不改输入position，不根据D选track。
- special明确标记独立几何/横向状态未定义，不能默认已经完成或普通pending。

### 13.2 小样本验收设计

1. 覆盖表6.3的12项边界；顶部/底部及左右相邻分别有可手算fixture。
2. 非连续PMT ID、同PMT pair多根route、距离并列、local_id=None均保留身份。
3. 给定commit集合前后比较，已完成对象退出pending，失败但未commit不自动退出。
4. 所有位置与ID前后相同，函数无输入修改；明确没有assignment输出。
5. 参数s/p分别列出，域外输入不强行clamp；不隐式选择floor/ceil。
6. M1不需要全量exact。若随后验证K预测，使用有限个解析fixture与既有exact函数标注“预测拒绝但exact安全 / 预测允许但exact multi / 一致”，不以检测器重复自证。
7. M1通过只表示D诊断有定义且可重复，不等于hierarchy可直接进入baseline。

后续若另行授权A/B/C试验，应固定输入哈希、端点、r/p/spacing、multi criterion及时间预算，分开比较hierarchy、fragment、exact接入方式。报告需同时给已处理/成功/耗尽/未完成数、track数与interval数、candidate成本和独立验证覆盖；未完成运行的全局指标标N/A。此处仅设计，不运行。

## 14. Open Ambiguities 与交付边界

关键未决问题：

1. K分母d与strip宽w+d不一致；IEEE Pitch=125 μm不能消除T歧义。
2. K的取整、窗口严格/非严格边界、是否包含候选、跨类别、空strip等。
3. 基础D布局参数与实际纵向中心线距离的精确前代实现映射。
4. 左/右危险邻居、底部反射、空pending、无危险候选、并列及域外政策。
5. 当前算法端点视图与前代方向、端口排序时序是否相同。
6. special参与pending、K与区域封锁的方式。
7. fragment编号列表与骨架范围/真实直段范围的对应；touch与零长度区间政策。
8. future方向需要查几条、是否使用同K；类别封锁精确边界与时点。
9. 论文实验输入与现有Excel是否完全相同。
10. T 4.4板尺寸及857/821计数口径；不能据此精确复现空间增益。
11. 论文100%不代表当前精确multi、finite width、clearance等全部约束验收通过。

**本轮交付**：仅本Markdown报告。未修改算法、默认策略、输入、旧输出或旧报告；未新建实现/测试；未安装依赖；未运行新routing或完整G1。420/420是Step L既有测试结果，不冒充本轮新测试。

**审计状态：有关键歧义。可以进入单独授权的M1诊断设计实现，不能直接把hierarchy/fragment加入正式baseline。本轮到此停止。**
