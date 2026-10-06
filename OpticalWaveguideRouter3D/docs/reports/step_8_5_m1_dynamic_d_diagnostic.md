# Step 8.5-M1：Read-Only Dynamic-D / Hierarchy Diagnostic

日期：2026-09-11。**M1 verdict：PASS（只读诊断范围）。不代表hierarchy已可用于allocator。**

## 1. Scope

本轮新增独立诊断模块、独立测试、可复现的小样本脚本和本报告。没有修改src/router_2d.py或其他已有实现，没有选track、拒绝candidate、改occupancy、assignment或route geometry。正式ascending、exclusive A、guard OFF、s=0.125 mm、p=0.175 mm、r=5 mm和multi criterion保持不变。

仅在回归测试中运行原有的小型算法测试；没有新512 routing、G1或全量exact validation。真实快照只读加载坐标，挑选四条代表route诊断。没有运行route451重放，也没有比较witness与Dynamic-D因果。

本轮文件：

- src/hierarchy_diagnostic.py：诊断逻辑，输出新建dict及标量副本。
- tests/test_hierarchy_diagnostic.py：38项独立测试。
- scripts/diagnose_dynamic_d_snapshot.py：只读、输出到stdout的四类快照小样本诊断。
- docs/reports/step_8_5_m1_dynamic_d_diagnostic.md：本报告。

继承审计：docs/reports/step_8_5_m_hierarchy_fragment_audit.md。本轮未产生新的论文终止端或危险侧证据；工程规则均标为PROJECT-SPECIFIC。

## 2. Data Model

接口为diagnose_dynamic_d，显式接收：

- 当前Waveguide与RoutePreparation。
- 调用者提供的algorithmic_endpoints二元组。
- PMT/Port目录、全部Waveguide目录。
- 每个route的显式route_statuses。
- 当前时刻的有序commit_prefix。
- special_route_ids，防止把special当普通横向待布线对象。
- 明确top_y/bottom_y，默认150/0；几何侧别tol默认1e-9。

不接受最终assignment来推断时序，不维护正式状态机，不新建Port/Route子类。

返回字段包括route_id、category、算法起终点副本、start_pmt/end_pmt、xt、terminal_side、current_scan_direction、论文排序/扫描对照、左右诊断、固定参数及commit_prefix副本。返回对象不与输入共享可修改的Port或Point2D。

错误也有明确状态：AMBIGUOUS、MISSING_ENDPOINT、INVALID_SIDE、UNSUPPORTED_GEOMETRY、UNSUPPORTED_GEOMETRY_FOR_HIERARCHY_DIAGNOSTIC。参数/坐标按带类型注解的接口接收；有限性、完整状态、唯一身份及几何可排序性进行检查。

## 3. Geometric PMT Adjacency

**PROJECT-SPECIFIC**：

1. 同一PMT所有Port必须位于同一明确top/bottom边界，且有有限Point2D坐标。
2. 以PMT端点的[min x,max x]作为几何范围。
3. 在每侧分别从左向右排序；端点范围相交或接触时返回AMBIGUOUS，不以PMT ID打破几何歧义。
4. 以当前算法终止PMT在该侧列表中的位置输出紧邻左/右PMT；不存在一侧为NO_ADJACENT。
5. 不把PMT ID±1作为邻接，不自动把存在的一侧选为危险侧。

同一PMT内允许不同port在相同x处形成手算并列fixture；不同PMT之间需能严格区分几何次序。目录每个Port必须有唯一route身份与显式状态，重复或游离身份不静默忽略。

真实快照64个PMT可以按此规则确定邻接；PMT中心、物理壳体范围并未创建。local_id=None不妨碍使用已有x坐标，也不被改写。

## 4. xt Mapping

调用现有只读prepare_waveguide_2d和_algorithmic_endpoints进行一致性核对，不复制或修改allocator。

当前工程U在端点x不同情况下取左端为算法起点；其余情况按现有(pmt_id,id)规则。输入algorithmic_endpoints若不符合当前helper则返回AMBIGUOUS。xt取算法终止端Point2D.x。

所有成功结果明确：

- terminal_mapping_status = CURRENT_PROJECT_ENDPOINT_VIEW
- dangerous_side = UNCONFIRMED
- direction_status = UNCONFIRMED_DIRECTION

**这不证明当前终止端等价于论文终止端。** M1确认的是当前工程视图可稳定读取，非前代算法方向已恢复。

## 5. Pending State Semantics

调用者必须为目录内每根route明确提供且仅提供一种状态：

| 输入状态 | 是否进入普通xa集合 |
|---|---|
| pending_for_horizontal_routing | 仅当不是当前route、不是special或unsupported时进入 |
| committed | 否 |
| failed_uncommitted | 否；不会因“未commit”自动改成pending |
| unsupported | 否，进入unsupported_related_routes |

commit_prefix需无重复，且其ID集合与状态为committed的集合精确一致。当前route不得在prefix中；当前普通诊断对象必须显式pending。prefix顺序由调用者声明，诊断不凭最终结果证明其历史真实性。

special_route_ids中的route即使被调用者标pending，仍单独列入unsupported_related_routes；记录其原输入状态以便审计，不把其重新解释为safe/dangerous。几何上属于不足2r的跨侧Z也被防御性隔离，避免遗漏special ID时误入普通候选。这沿用当前ordinary跨度界限，不创建新的special算法。

状态A→B测试仅将route2从pending改为committed并更新prefix：[2]。左侧候选route2退出，最近者改成route3；所有位置、ID、PMT、local_id与waveguide数据不变。failed_uncommitted有独立排除测试。

## 6. Left / Right Dynamic-D

每个邻接结果分别保存：

neighbor_pmt、pending_count、pending_candidates、nearest_candidates、nearest_distance、unsupported_related_routes、excluded_candidates、continuous。

每个端点记录route_id、port_id、pmt_id、local_id、x、y、route_status。同PMT pair的多条route不合并，最近距离按abs(xt−x)计算。

| 情况 | 邻接status | 距离语义 |
|---|---|---|
| 邻居不存在 | NO_ADJACENT | nearest_distance=None，无连续公式结果 |
| 邻居存在但普通pending为空 | NO_PENDING | nearest_distance=None，不输出0/inf |
| 唯一最近者 | OK | 实测最小D |
| 多个等距最近者 | TIE_NEAREST | 保留所有最近端点及route身份 |
| D超出公式分支 | 邻接仍可OK/TIE_NEAREST，continuous.status=OUT_OF_FORMULA_DOMAIN | D仍有效；仅L及比值不可用 |

**PROJECT-SPECIFIC 并列规则**：对计算出的浮点距离使用精确相等，不隐式引入新的近似并列容差。候选按(x,port_id)稳定排序；因此输入PMT、route及port列表重排不改变输出。若未来需要容差并列，必须另行明确政策，不能伪称论文规定。

顶层OK表示输入和当前视图可诊断，不代表两侧都有候选，也不表示公式适用或几何安全；各层status保留原因，避免将多个问题压成None。

## 7. Four Ordinary Categories

分别输出类别元数据，不根据“ascending baseline”假定所有track均升序：

| 类别 | 当前默认primary x | 当前y扫描 | terminal side | 论文primary x / y扫描 |
|---|---|---|---|---|
| top-U | ascending | descending | top | ascending / descending |
| bottom-U | ascending | ascending | bottom | ascending / ascending |
| top->bottom Z | ascending | descending | bottom | descending / ascending |
| bottom->top Z | ascending | descending | top | descending / descending |

表中当前元数据指正式ascending baseline，不冒充Step L descending实验入口的完整配置。特别是top→bottom Z同时存在x顺序和y扫描差异，bottom→top Z有x顺序差异。左右邻居按终止侧独立计算，不指定哪一侧危险。

四类synthetic均通过：xt=20，左右D=2，终止侧及扫描方向各自正确。真实样本结果见第12节。

## 8. Special-Z Handling

当前route为special时，返回UNSUPPORTED_GEOMETRY_FOR_HIERARCHY_DIAGNOSTIC，不计算左右D或L；仍可显示当前工程端点来源信息，但不当普通horizontal route。

邻接PMT中的special独立列于unsupported_related_routes，即使它在输入状态中被标pending，也不会混入普通xa集合。显式unsupported的其他route也在该独立列表保留。

真实快照识别58条special-Z；本轮未生成或修改其解析geometry。四个样本的邻接列表中special的隔离数量及ID见第12节。没有决定special是安全、危险、已完成或等待普通horizontal assignment。

## 9. Formula Domain

独立continuous_hierarchy_diagnostic只计算：

L = r − sqrt(r² − (r+s−D)²)

固定s=0.125 mm、p=0.175 mm、r=5 mm。

**PROJECT-SPECIFIC 审计分支**：只在s≤D≤r+s，即0.125≤D≤5.125 mm内使用该较小根表达式。这是Step M明确的非负根号下界/相关几何分支，不是论文给出的完整程序分支，也不是仅检查根号实数就任意延伸。

D非有限、D<s或D>r+s时返回OUT_OF_FORMULA_DOMAIN；不clamp，不自动返回K=0，不把原不等式在大D下可能自动满足解释为继续用该公式。

边界D=s给L=r=5；D=r+s给L=0，这是公式有效边界真实值，不是NO_PENDING的代用值。原文边界/取整歧义仍保留，诊断值不控制allocator。

## 10. L/s vs L/p

有效D同时返回：

- L_mm：连续长度。
- paper_ratio=L/s。
- project_pitch_ratio=L/p。

不输出整数K，不调用floor、ceil、round或int来处理这些量。

手算fixture：D=2.125时r+s−D=3，sqrt(25−9)=4，L=1 mm，L/s=8，L/p=40/7≈5.714285714285714。测试分别验证，不能把两种比值合并。

## 11. Synthetic Fixtures 与回归

新增38项测试全部通过：

- top/bottom中间PMT、最左/最右、左右及两侧NO_PENDING。
- 几何邻接、非连续ID、local_id=None、同pair多route。
- 唯一最近、并列全部保留、显式committed与failed排除、当前route自身排除。
- 状态变化、prefix不一致/重复、状态不完整/未知。
- 四类ordinary、论文Z方向差异、算法端点视图不一致。
- special邻接隔离、当前special拒绝诊断、未显式列出的短Z隔离。
- 公式手算值、有效边界、域外/非有限输入、L/s和L/p分离。
- 输入深拷贝相等、输出修改不影响输入、目录顺序改变仍确定。
- 缺失坐标、非法侧别、PMT范围重叠显式报告。
- 无K、track_index、assignment、occupancy输出字段。

使用项目现有Python 3.10环境和标准库运行测试函数；未安装pytest或新依赖。按每个tests/test_*.py中的test_*函数逐项执行，异常即失败，与现有零参数测试结构一致。

| 测试文件 | 通过数 |
|---|---:|
| test_collision.py | 98 |
| test_double_cross_audit.py | 15 |
| test_geometry.py | 63 |
| test_hierarchy_diagnostic.py | 38 |
| test_io.py | 28 |
| test_loss.py | 26 |
| test_loss_analysis.py | 17 |
| test_models.py | 18 |
| test_multi_crossing.py | 20 |
| test_multi_crossing_delta.py | 13 |
| test_multi_crossing_guard.py | 43 |
| test_physical_intersections.py | 19 |
| test_router_2d.py | 48 |
| test_top_u_order.py | 12 |
| **合计** | **458** |

原420项全部通过，新增38项通过，失败0。全套运行约4.99秒，未发现测试警告或错误。原有单元测试包含微型allocator/exact样例，不等于本轮新运行512实验。

## 12. Real Snapshot Samples

### 12.1 来源与明确状态

只读输入：

- C:/Users/lihao/Desktop/Graduation Project/自动排布/AutoRouter/fiberBoard512.xlsx
- C:/Users/lihao/Desktop/Graduation Project/自动排布/AutoRouter/fiberBoard0data.xlsx

加载512 Waveguide / 64 PMT，58 special。源文件SHA256读前读后相等：

- fiberBoard512.xlsx：71a19ec1739de75453608d1d9bd0bb2b9ad102140e4af5057c12e60c0accd7ff
- fiberBoard0data.xlsx：6901bd1f15388cf15831b57297be9a6a6f51ef1d661196e282dc5f1bbd6a8770

**PROJECT-SPECIFIC 假设时刻**：全部ordinary显式pending_for_horizontal_routing；58 special显式unsupported；commit_prefix=[]。这不是初始allocator真实状态的考证，不是任何Step L历史时刻，不从最终assignment反推。

脚本对完整输入对象、状态集合及prefix做前后深拷贝相等检查通过。每类只诊断首个代表route，未调用assign_tracks_2d或生成路径。

| route_id | 类别 | 算法start PMT → end PMT | xt (mm) | 当前扫描 | 终止侧 |
|---|---|---|---:|---|---|
| 36 | top-U | 12 → 8 | 130 | descending | top |
| 9 | bottom-U | 54 → 1 | 119.7 | ascending | bottom |
| 17 | top->bottom Z | 2 → 56 | 20.525 | descending | bottom |
| 0 | bottom->top Z | 1 → 8 | 132.1 | descending | top |

### 12.2 左右结果

| route_id | 侧 | 邻接PMT | 普通pending数 | 最近route ID | xa (mm) | D (mm) | 单列special IDs |
|---|---|---:|---:|---|---|---|---|
| 36 | left | 93 | 16 | 333 | 128.125 | 1.875 | 无 |
| 36 | right | 61 | 12 | 454 | 134.5 | 4.5 | 256,257,258,259 |
| 9 | left | 72 | 16 | 292 | 117.125 | 2.575000000000003 | 无 |
| 9 | right | 73 | 13 | 319 | 123.5 | 3.799999999999997 | 342,343,344 |
| 17 | left | 80 | 15 | 392 | 18.125 | 2.3999999999999986 | 501 |
| 17 | right | 81 | 16 | 511 | 24.5 | 3.9750000000000014 | 无 |
| 0 | left | 93 | 16 | 333 | 128.125 | 3.9749999999999943 | 无 |
| 0 | right | 61 | 12 | 454 | 134.5 | 2.4000000000000057 | 256,257,258,259 |

八个邻接结果均有唯一最近者，status=OK；四条的dangerous_side均为UNCONFIRMED。表中保留浮点运算实际表示，例如2.575000000000003，未为显示而改变计算结果。

### 12.3 连续结果

| route_id | 侧 | 公式status | L_mm | L/s | L/p |
|---|---|---|---:|---:|---:|
| 36 | left | OK | 1.200328961607334 | 9.602631692858672 | 6.859022637756195 |
| 36 | right | OK | 0.03921629175389274 | 0.3137303340311419 | 0.22409309573652997 |
| 9 | left | OK | 0.69912799539442 | 5.59302396315536 | 3.9950171165395436 |
| 9 | right | OK | 0.17875794011543178 | 1.4300635209234542 | 1.021473943516753 |
| 17 | left | OK | 0.807819779637331 | 6.462558237098648 | 4.616113026499034 |
| 17 | right | OK | 0.13404685595925603 | 1.0723748476740482 | 0.7659820340528917 |
| 0 | left | OK | 0.1340468559592578 | 1.0723748476740624 | 0.7659820340529018 |
| 0 | right | OK | 0.8078197796373265 | 6.462558237098612 | 4.616113026499009 |

这些值仅证明在给定显式状态下计算可重复；不构成multi改善、K策略有效或布通率提升证据。

复现入口（项目根目录，stdout输出完整端点列表，不写原数据）：

```powershell
.\.venv\Scripts\python.exe -B -m scripts.diagnose_dynamic_d_snapshot "C:\Users\lihao\Desktop\Graduation Project\自动排布\AutoRouter\fiberBoard512.xlsx" "C:\Users\lihao\Desktop\Graduation Project\自动排布\AutoRouter\fiberBoard0data.xlsx"
```

### 12.4 route451

**NOT RECONSTRUCTABLE FROM SAVED STATE**，限定为本Step所需完整显式时刻状态。

只读检查Step L fast_routing、partial_geometry及exhaustion_summary的保存结构和既有审计：有已提交geometry、拒绝/失败、assignment及commit证据，但没有为全部相关对象持久化pending_for_horizontal_routing与special横向状态。已知44条commit前缀的证据不自动授权将所有其余route划为论文pending。

本轮没有填route451的D，没有重放candidate，没有把失败/unsupported对象自动补成pending。此限制不否认Step L已完成的21条exhaustion和witness正确性审计。

## 13. Remaining Ambiguities

1. 当前工程算法终止端是否忠实等于论文终止端，仍未确认。
2. 哪一侧是危险邻接、各类别的几何危险过滤规则，仍未确认。
3. special横向时序未定义，本轮仅隔离。
4. K分母、离散取整、窗口边界、区域锁定等不在M1决定范围。
5. 几何范围重叠/接触或坐标缺失的其他数据集返回明确歧义；不补坐标、不按ID选邻居。
6. 当前精确浮点并列语义是显式工程约定，不是论文规定。
7. 给定prefix与显式状态可以校验一致性，但不能凭接口证明它们来自真实历史；调用者负责来源。
8. 四条真实样本采用假设状态，只能作可重复性示例，不可包装为Step L因果解释。

这些未决项阻止直接采用正式hierarchy，却不阻止本Step限定的当前工程endpoint view、显式状态、双侧距离诊断。

## 14. M1 Verdict

**PASS**：

- PMT几何邻接可确定。
- 当前工程xt可稳定获得，未声称论文映射已证实。
- 给定完整显式状态，两侧xa与D可重复。
- 空邻接、空pending、并列和输入歧义均有独立语义。
- 四类ordinary及special隔离通过测试。
- s与p分离，只有连续L及比值，不选择整数K。
- 全部458项测试通过。
- 不修改任何allocator行为，不执行新全量routing。

交付前对既有src/tests/scripts/outputs/docs文件做SHA256核对；仅新增本轮四个文件，既有117个受保护文件保持不变。原始Excel哈希亦保持不变。

**本轮停止，不进入M2、fragment或正式hierarchy实现。**
