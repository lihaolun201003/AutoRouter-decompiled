# 2 原程序复现与几何一致性

本章回答：第 3 章以后所有"相对原版改善"说法的参照物有多可靠。所有损耗都是**现有损耗模型的计算值，不是器件实测值**。

## 2.1 从旧 AutoRouter 到 Python 3.10 的恢复过程与输入恢复

复现对象是 2020-06-19 构建、PyInstaller 打包的 `AutoRouter.exe`。恢复没有停在反编译文本上：从 `PYZ-00.pyz` 取出未 marshal 的 code object，用 `xdis` 按 Python 3.8 语义反汇编字节码作算法基线，反编译可疑处一律以字节码裁定 [OpticalWaveguideRouter2D/docs/migration_report.md]。原 exe 实跑写出的两个文件被当作金标准：端口布置 `fiberBoard0data.xlsx` 与直线布线图 `fiberBoard512_rect.pdf`。

输入恢复分两半。连接表是真实的：256 / 512 各 256 / 512 行、只有 `Port1`/`Port2` 两列的 `fiberBoard256.xlsx` / `fiberBoard512.xlsx`，SHA-256 与随 EXE 发布的副本一致（512 为 `71a19ec1…`）[OpticalWaveguideRouter3D/docs/reports/step_8_5_route_level_intersections_v01.md]。端点坐标只有 512 有：`fiberBoard0data.xlsx`（512 行 × 11 列，含 `index1/index2/sy/ly/dz/sx/lx/dx`，SHA-256 `6901bd1f…`）是原程序自己写出的**历史坐标快照** [OpticalWaveguideRouter2D/results/fiberBoard0data.xlsx]。256 既无坐标快照也无参照图，其端点布局由 `create_sim_space` 按同一算法**生成**，不能从 512 公式截半充当 [OpticalWaveguideRouter3D/docs/2d_routing/parameters_and_ports.md]。

## 2.2 轨道与直线/圆弧构造

原版把每条路线放进一条水平轨道，四个布线遍各有扫描方向与边界约束；`noCross` 用前 3 / 后 7 等窗口检查已有波导。复现在 Python 3.10 上重建 `plotter_rect` 的轨道选择，复现产物 `fiberBoard256bend.xlsx` / `fiberBoard512bend.xlsx` 各 256 / 512 行、20 列（含 `inflection`、`bend_x/y`、`center`、`theta` 等），由本次直接读表确认。按`inflection` 统计：256 使用 **245** 条轨道（候选 467 条、0.30 mm 步距、5.0–144.8 mm），其中 **8** 条被多条路线共用，同轨区间重叠 **0** 处；512 使用 **477** 条轨道（候选 800 条、0.175 mm 步距、5.0–144.825 mm），**25** 条共用，重叠 0 [OpticalWaveguideRouter2D/results/fiberBoard256bend.xlsx]、[OpticalWaveguideRouter2D/results/fiberBoard512bend.xlsx]。按 `dx≥2R` 划分，256 有 31 条、512 有 58 条属于 `0<dx<2R` 的非完整双弧特例。

`plotter_bend` 的切点、圆心、角区间与象限方向按**行进方向**重建成 Line/Arc 解析段序列，这是后续解析求交与损耗计算的前提。

## 2.3 对照方法与对照层级

资料中存在两种证明力完全不同的对照。

**其一，与旧图对照。** 2020 年 `fiberBoard512_rect.pdf` 只有 266/512 一致（235 条差恰好一根轨道、11 条更多）：`above→above` 112/112、`below→above` 115/115 一致，`below→below` 仅 39/112 精确、62 条高一档，`above→below` **0/173 全部统一高一档** [OpticalWaveguideRouter2D/docs/debug_first_divergence.md]。差异只落在依赖 `MTbelow` 的 `noCross` 分支，`above→below` 的整块偏移可由 `below_line = max(df2["inflection"])` 单一原因解释。旧图来自**另一个构建**，既不能证明复现正确，也不能作数值基准。

**其二，与原可执行程序（字节码）对照。** 项目用官方 Python 3.8.10 嵌入式解释器 + 从包里取出的 NumPy 1.18.5 / pandas 1.0.4 / gdspy，**原样执行原程序代码对象**，并用 `sys.settrace` 记录内部状态。结果：`create_sim_space` 对 2020 快照 512/512 行、列值最大偏差 0；`plotter_rect` 512/512 同轨道；`plotter_bend` 全部列 512/512 一致；`svg2gds_bend` 512/512 路径点阵与宽度一致，仅 8 个时间戳字节不同 [OpticalWaveguideRouter2D/docs/exact_legacy_fidelity_report.md]。逐路状态差分显示 `MTbelow` 快照最大偏差 0，**复现与原可执行程序之间不存在第一处分歧**。

| 对照层级 | 对照对象 | 一致程度 | 能证明什么 | 不能证明什么 | 来源 |
| --- | --- | --- | --- | --- | --- |
| 图形对照 | 2020 年 `fiberBoard512_rect.pdf` | 266/512（52%） | 两个构建的差异位置与形态 | 不能证明复现正确；该图来自另一构建 | `OpticalWaveguideRouter2D/docs/debug_first_divergence.md` |
| 数值对照 | 前代论文 4.1–4.3 印刷值 | 6 个数字全部落入一位小数精度 | 损耗量级与半径趋势 | 不能证明几何逐条一致 | `OpticalWaveguideRouter3D/publication/tables/t32_reproduction_compare_data.csv` |
| 字节码状态对照 | `AutoRouter.exe` 解包代码对象（Py3.8.10 实跑） | 端点 / 轨道 / 弯曲参数 / GDS 点阵 512/512 一致 | 复现与原可执行程序逐阶段等价 | 不能证明交叉损耗项（原表缺失） | `OpticalWaveguideRouter2D/docs/exact_legacy_fidelity_report.md` |
| 不变量对照 | 256 自身产物 | 行数、轨道合法、无同轨重叠、几何有限 | 256 结果自洽可用 | **256 无原版参照，无法证明与原件一致** | `OpticalWaveguideRouter2D/docs/migration_report.md` |

注：表 2-1 的字节码状态对照只覆盖 512。

## 2.4 损耗模型的数字化近似

传播项取论文表 2-1 的 **0.05 dB/cm**，与原版 `calc_loss` 的 `straight_loss = -0.005` dB/mm 等价。弯曲项来自原版硬编码的 `tl`/`ll` 两表，密度乘 90° 弧长可复算出论文表 3-1 的 7.94/6.81/4.59/2.39/1.90 dB，五位全部吻合到两位小数，说明论文表就是这批密度的四舍五入；复现实现的是原始密度（R5 用 2.3826 而非 2.39）[OpticalWaveguideRouter3D/publication/tables/t31_bend_model_thesis_vs_repro_data.csv]。

**交叉项是真正的缺口。** 原版按整数角度从外部传入的 DataFrame 取 `loss_db`，该表未随 EXE 发布；对 PYZ 条目、exe 二进制、随附压缩包、全目录 xlsx/xls/csv 与被调用处的穷尽搜索均无结果 [OpticalWaveguideRouter2D/docs/loss_model_reconstruction_report.md]。现用表由论文图 3-12 的 "cross number 30" 曲线数字化，并按论文文字"90° 约 0.05 dB"以 0.05/0.0593 缩放锚定。原图曲线自身抖动约 0.1 dB，远大于单次交叉损耗（0.05/30≈0.0017 dB），**只有趋势可信，绝对高度不可信**。三口径固定几何复算给出 5.4758 / 5.5147 / 5.5745 dB，跨度 0.0986 dB [OpticalWaveguideRouter3D/publication/tables/t34_crossing_model_sensitivity_data.csv]。全部损耗为模型计算值。

| 缺失／不确定项 | 现状 | 后果 | 来源 |
| --- | --- | --- | --- |
| 原版交叉损耗表（`angle`/`loss_db`，30 交叉） | 本机不可得，已穷尽搜索 | 交叉项用标注过的数字化近似，整链损耗带约 0.1 dB 模型不确定度 | `OpticalWaveguideRouter2D/docs/loss_model_reconstruction_report.md` |
| 256 的半径配置与独立半径实验 | 未确认 | 256 不能给出"间隔:半径"比值，不能与 512 半径结论互换 | `OpticalWaveguideRouter3D/docs/2d_routing/parameters_and_ports.md` |
| 旧 EXE 的默认半径 | 未确认 | 5 mm 是论文实验值与当前解析几何取值，不等于旧 EXE 默认值 | `OpticalWaveguideRouter3D/docs/reports/step_8_legacy_track_assignment_audit.md` |
| 输入/输出耦合与连接器数据 | 不足 | 现有数值只是部分预算，不是完整链路损耗 | `OpticalWaveguideRouter3D/docs/2d_routing/parameters_and_ports.md` |
| 论文 4.2 的单位（PMT 宽 4.8、间距 4.2、区域 150 印为 μm） | 印刷矛盾，未静默修正 | 按记录原值处理，复现用 250 μm 间距与 150 mm 区域 | `OpticalWaveguideRouter2D/docs/loss_model_reconstruction_report.md` |

## 2.5 复现可靠性结论

**已支持（逐位一致）：** 512 的端点布置、轨道选择、弯曲参数、GDS 点阵与原可执行程序完全一致；弯曲/传播损耗参数可追溯到原版内部表并互相印证。

**仅图形一致（不构成证据）：** 与 2020 年旧图的 52% 一致度；旧图属另一构建，只作历史记录。

**未验证：** 256 的正确性只有不变量支撑，无原版参照；交叉损耗表缺失，交叉项是标注过的近似。

**两项必须保留的口径警告：** ① 全部损耗是模型计算值，非实测值。② 早期的传播 / 弯曲估算（3D 项目 Step F：ordinary 平均已知非交叉损耗 5.4631 dB、最大 6.1874 dB，`crossing_loss` 仍为 `NotImplementedError`）**不等于完整链路损耗** [OpticalWaveguideRouter3D/docs/reports/step_8_5_loss_and_angle_v01.md]；含交叉近似的 512 R5 全项值为 5.5147 dB [OpticalWaveguideRouter2D/results/fiberBoard512_loss_summary.json]。这两个数字口径不同，不得并列比较。

另有两处本次核查发现的口径不一致。(a) `migration_report.md` 正文写"256：243 使用 / 10 共用；512：475 使用 / 25 共用"，与随包产物及 `tools/verify_reconstruction.py` 的判据均不符——按原始 xlsx 复算为 **245 / 8** 与 **477 / 25**，产物文件大小与时间戳表明报告写定后未再重跑，故以原始产物为准。(b) 3D 项目 opt2d 的 "A-R5-legacy" 臂与 2D 复现不逐位等同：512 平均/最大 5.5162 / 6.5773 dB（2D 5.5147 / 6.5761）、交叉项 86,786（2D 86,512）、最小交叉角 23.074°（2D 14.0°）[OpticalWaveguideRouter3D/outputs/opt2d/512/comparison.csv]、[OpticalWaveguideRouter2D/results/fiberBoard512_loss.xlsx]；差异约 1e-3 dB，原因本轮未定位（候选因素：原版分段折线求交与 3D 精确 Line/Arc 内核的计数差异，或同侧连接 U 型构造差异）。涉及"原版几何"的数值一律以 2D 复现为基准。

---

# 7 排序、多交叉防护与局部恢复

本章记录的是**实验，不是成品算法**。正式基线始终为 ascending + exclusive A + G1 + guard OFF（宽 0.05 / 间距 0.125 / 节距 0.175 / 半径 5 / 板高 150 mm）。

## 7.1 Top-U 主排序反转 A/B

基线主排序键 `(group, start.x, end.x, start.pmt_id, end.pmt_id, id)` 全部升序。实验只改一个变量：group 0（Top-U）的 primary x 取反（降序），次级 x、PMT ID、波导 ID 的平局次序不变，其余分组与 G1/A/S1 不动 [OpticalWaveguideRouter3D/docs/reports/step_8_5_top_u_order_ab_v01.md]。

112 条 Top-U 的路线—轨道映射全部改变，但占用轨道索引集合 688..799 不变，非 Top-U 的 `TrackAssignment` 与解析几何逐条相等（isolation 五项全 True）。主要结果是 **topU-topU 双交叉对 1903 → 0**；嵌套端点对关系不随轨道分配改变，同样的 1903 → 0 在骨架层就已出现，说明改善发生在平滑之前。连带收益：物理交点 55935 → 52129（−3806）、有交叉路线对 49502 → 47599（−1903）、双交叉对总数 6433 → 4530、全局 <20° 交叉 1508 → 984、平均交叉角 78.636° → 79.822° [OpticalWaveguideRouter3D/outputs/step_8_5_top_u_order_ab_summary.json]。

**同一实验同时给出反向证据：** 多波导交叉判据（三交点三角形至少两边 < 0.125 mm）的检出数由 **318 升到 345（+27，+8.49%）**，而 eligible 三角形集合完全不变（1,222,071），boundary 仍为 2。因此这不是全面改善 [OpticalWaveguideRouter3D/docs/reports/step_8_5_top_u_order_ab_v01.md]。全局平均长度、传播损耗、弯曲损耗、已知非交叉损耗的均值与最大值均不变（138.3424 mm / 5.2646 dB），但个别 Top-U 长度被重分配：全局最短长度 31.8830 → 21.4330 mm。

## 7.2 多交叉差分审计与精确几何 guard 负实验

**差分审计（只读）。** 对 318 与 345 两个集合做 canonical 三元组比对：stable 204、removed 114、added 141，净 +27，实际周转 255 个三元组而非 27 个。所有 added / removed 都含 Top-U，204 个 stable 全部不含；graph 三角形由 2,063,548 降到 1,835,220（移除 228,328、新增 0），而 eligible 集合 1,222,071 完全不变。这说明机制是**同一批 eligible 三元组内三个已存在交点的位置改变**导致阈值进出，而非新生成了 eligible 资格 [OpticalWaveguideRouter3D/docs/reports/step_8_5_top_u_multi_crossing_delta_v01.md]。新增项并非都卡在阈值边缘：141 个 added 中 87 个（61.7%）余量 >0.05 mm，但 added 含 <20° 交叉 26 个，多于 removed 的 18 个。

**精确几何 guard（负实验）。** 在 G0/G1 均固定 descending 的前提下做 guard OFF/ON 对照：每个候选生成真实 Line/Arc 临时几何并与已提交路径求精确交点，用**现有** `classify_multi_crossing` 判定，明确 multi 才拒绝。G0 gate（130,816 对）通过；但完整 G1 的候选级诊断成本过高，**本轮被中止，未产生 G1 结论** [OpticalWaveguideRouter3D/docs/reports/step_8_5_exact_multi_guard_ab_v01.md]。

随后的有界试运行采用 180 秒上限（性能门槛，非路由约束）：routing 未完成，已 commit ordinary **217**（不是最终布通率）、已确认 guard 耗尽 **21**、candidate attempts 14,914、明确 multi 拒绝 14,696，其中 pair kernel 约占 86.5% wall time。fast rejection 路径在固定小样本（40 条已提交路径、重复 30 次）上把 median 从 0.003903 s 降到 0.000528 s（约 7.39 倍），**该倍率只对该 workload 成立，不是 512 全量加速比**。

最终审计结论是 **G1 FAILS ROUTABILITY REQUIREMENT**：21 条失败均已完成全量扫描并拒绝所有基础可用候选（不是被 180 秒截断），14,384 次拒绝经独立重算 43,152 组 witness 对复核通过（交点/边长最大偏差约 2.8e-14 mm）；事务重放对 451/427/428/430 的五类状态 SHA-256 前后相等。route 451 的 756 个基础可用候选全部被拒。21 条中 top-U 14 条、top→bottom Z 7 条。准确含义是：**当前这一具体 greedy hard-guard 组合（descending + exclusive track + R5 + 精确 multi 硬拒绝 + 无 reroute/fallback）不能同时满足 multi 规避与 100% ordinary 可布通**，不扩展为所有多交叉规避方案不可行 [OpticalWaveguideRouter3D/outputs/step_8_5_exact_multi_guard_exhaustion_summary.json]。

## 7.3 局部精确恢复的可行性与边界

M1.5 把正式基线的 318 个 multi 全部归因（954 = 3×318，798 个唯一路线对）：318/318 都涉及**端点相连弯曲**，仅 LEFT 265、仅 RIGHT 23、混合 30；最常见简单 signature 为 Arc×H | Arc×V | H×V，287/318（90.25%）[OpticalWaveguideRouter3D/docs/reports/step_8_5_m1_5_exact_multi_attribution.md]。

M1.6 只做**固定案例的离线沙箱验证**：单 victim 精确恢复即移除一条 ordinary，重算该 victim 的 511 个 pair 与含它的三元组，按 `(M_after, new_multi_created, |轨道位移|, 轨道索引)` 字典序取最优，且只接受整数 M 严格下降。四个固定案例各扫描 347 个候选（346 替代 + 1 原位）共 1,388 个，几何全部合法：M0011 最小 M_after = 318（**无严格改进候选**）、M0009 = 317、M0001 = 316、M0023 = 316。三次下降各自从原 318 基线出发，**不可相加，也不是连续恢复后的 313**。winner 经独立入口重算 511 个 star pair 与 37,128 / 4,371 / 5,995 个固定第三边，未做全 512 all-pairs 重跑；原位回放 4 例均 M=318、目标保留、delta 为空 [OpticalWaveguideRouter3D/outputs/step_8_5_m1_6_probe_summary.json]。

边界同样明确：state 为 `FEASIBILITY_ONLY_NO_COMMIT`，**没有任何正式 recovery commit**，事务方案（版本检查 + 原子交换状态根）只被规定、未被实现；M0011 只能标 `FIRST_VICTIM_EXHAUSTED`，不能标 `SINGLE_VICTIM_UNRECOVERABLE`；未尝试第二/第三 victim、未做 318 循环、depth-2 或递归。设计文件与检查点属同一项工作，只计一个实验 [OpticalWaveguideRouter3D/docs/reports/step_8_5_m1_6_checkpoint.md]。

K/M 两项审计均为**只读**：K 指出论文 K 式的 d 与 pitch、基础 D、整数化与窗口边界、域外处理均未确认，故不实现"忠实 legacy K"；M 补充论文 4.1 的 PMT 间距 1.7 mm 仍与实测纵向端点间距 1.875 mm、原点节距 4.5 mm 并存，不能无歧义选定 [OpticalWaveguideRouter3D/docs/reports/step_8_5_legacy_optimization_compatibility_audit.md]、[OpticalWaveguideRouter3D/docs/reports/step_8_5_m_hierarchy_fragment_audit.md]。

| 实验 | 变量 | 规模 | 关键结果 | 证据等级 | 来源 |
| --- | --- | --- | --- | --- | --- |
| Top-U 主排序反转 | Top-U primary x 升序 → 降序 | 512（454 ordinary + 58 special） | 1903→0 双交叉；318→345 multi（+27） | **完整布局实验** | `OpticalWaveguideRouter3D/outputs/step_8_5_top_u_order_ab_summary.json` |
| 多交叉差分审计 | 无（只读比对） | 318 vs 345 三元组 | stable 204 / removed 114 / added 141；eligible 不变 | 只读审计 | `OpticalWaveguideRouter3D/outputs/step_8_5_top_u_multi_crossing_delta_summary.json` |
| exact multi guard A/B | guard OFF/ON（G0/G1 固定 descending） | G0 130,816 对；G1 未完成 | 180 s 上限触发，217 committed、21 exhausted | **有界中止 + 候选耗尽** | `OpticalWaveguideRouter3D/outputs/step_8_5_exact_multi_guard_exhaustion_summary.json` |
| 局部精确恢复探针 | victim 轨道位置 | 4 案例 × 347 候选（离线） | 318→317/316/316；M0011 无改进 | **离线沙箱，未 commit** | `OpticalWaveguideRouter3D/outputs/step_8_5_m1_6_probe_summary.json` |
| K / M / M1 审核 | 无（只读） | 论文式 3-10—3-15 与快照 | K、D、fragment 语义未闭合，不实现 | 只读审计 | `OpticalWaveguideRouter3D/docs/reports/step_8_5_m_hierarchy_fragment_audit.md` |

## 7.4 证据等级分类

表 7-1 的"证据等级"列即逐条标注：完整布局实验 1 项、有界中止 + 候选耗尽 1 项、离线沙箱 1 项、只读审计 3 项。该列只描述实验完成度，不代表结论强度；有界中止与候选耗尽均不得当作完整布局结果。

| 负结果／未完成项 | 事实 | 来源 |
| --- | --- | --- |
| 排序反转不是全面改善 | multi 检出 318→345（+27），added 141 中含 26 个 <20° 交叉 | `…/step_8_5_top_u_multi_crossing_delta_v01.md` |
| hard guard 不可布通 | G1 FAILS ROUTABILITY；21 条真实耗尽；route 451 的 756 个候选全被拒 | `…/step_8_5_exact_multi_guard_ab_v01.md` |
| guard 全量实验未完成 | 完整 G1 被中止，final 指标记为 `N/A — incomplete routing` | `…/step_8_5_exact_multi_guard_exhaustion_summary.json` |
| 加速比被限定 | 7.39× 仅来自 40 条路径的固定小样本 | `…/step_8_5_exact_multi_guard_ab_v01.md` |
| 恢复未落地 | 无 COMMIT；4 案例不可相加；M0011 仅第一 victim 耗尽 | `…/step_8_5_m1_6_checkpoint.md` |
| legacy K 不可实现 | d/pitch、基础 D、整数化、域外处理均未确认 | `…/step_8_5_legacy_optimization_compatibility_audit.md` |
| fragment 与本报告 A 冲突 | 需把 track 占用改为一对多，改变 A 的语义 | `…/step_8_5_m_hierarchy_fragment_audit.md` |
| 交叉损耗缺失 | Step 8.5 全阶段 `crossing_loss` 为 `NotImplementedError`，未调用 | `…/step_8_5_loss_and_angle_v01.md` |

---

# 附：参数事实清单（供第 1 章使用）

| 项 | 256 | 512 | 来源 |
| --- | --- | --- | --- |
| 连接输入 | `fiberBoard256.xlsx`（256 行，仅 `Port1`/`Port2`） | `fiberBoard512.xlsx`（512 行，同上；512 行含 `=A2+60` 类公式） | `OpticalWaveguideRouter3D/docs/reports/step_8_legacy_input_validation.md` |
| 端点坐标来源 | **算法生成**（`create_sim_space`，无独立快照／参照图） | **历史坐标快照** `fiberBoard0data.xlsx`（512×11，原程序实跑写出） | `OpticalWaveguideRouter2D/docs/migration_report.md` |
| 板尺寸 | 150 mm × 150 mm | 150 mm × 150 mm | `OpticalWaveguideRouter3D/docs/2d_routing/parameters_and_ports.md` |
| 波导宽度 | 0.05 mm（50 μm） | 0.05 mm（50 μm） | 同上 |
| 边缘间隔 | 0.25 mm（250 μm） | 0.125 mm（125 μm） | 同上 |
| 轨道节距 | 0.30 mm | 0.175 mm | 同上 |
| 弯曲半径 | 5 mm（独立半径实验未确认） | 5 mm（论文实验值；旧 EXE 默认值未确认） | 同上 |
| 端口布局 | 32 个 PMT × 16 端点 = 512 端点 | 64 个 PMT × 16 端点 = 1024 端点；下边 `(2+4.5c+0.175j, 0)`、上边 `(4+4.5c+0.175j, 150)` | 同上 |
| 轨道数 | 复现使用 245 / 候选 467 | 复现使用 477 / 候选 800 | `OpticalWaveguideRouter2D/results/fiberBoard{256,512}bend.xlsx` |

注：**R5 / R6 是弯曲半径 5 mm / 6 mm，不是实验编号**；半径扫描的 R2/R3/R4/R5 分别对应 2/3/4/5 mm [OpticalWaveguideRouter2D/results/fiberBoard512_loss_R{2,3,4}_summary.json]。实验编号（`step_12`、`512`、`01_xxx`）是另一套编号，不可混用。2D 复现轨道网格起点 5.0 mm，3D opt2d 的 G1 起点 5.025 mm（`r+w/2`），二者口径不同 [OpticalWaveguideRouter3D/docs/reports/step_8_5_m1_6_local_exact_recovery_design.md]。
