<!-- pagebreak -->
# 7 排序、多交叉防护与局部恢复

本章的对象是**实验记录，不是已完成的成品算法**。这些工作在时间上早于第 3–6 章，属于原版 512 布局上的排序与防护探索，规模固定在 512 通道（454 条普通路线 + 58 条特殊 Z 形）。正式基线始终是"升序主排序 + exclusive 轨道 + G1 网格 + guard 关闭"（宽 0.05 mm、间距 0.125 mm、节距 0.175 mm、半径 5 mm、板高 150 mm）。

## 7.1 证据等级：先分类，再读结论

本章所有条目按**完成度**分级。等级只描述实验做到哪一步，不代表结论强度。

| 等级 | 含义 | 可以作为什么使用 |
| --- | --- | --- |
| **完整布局实验** | 全规模跑完，产出完整布局与指标 | 可以作为结果引用 |
| **有界中止** | 因时间/成本上限主动停止，布局不完整 | 只能描述该次运行的中间状态 |
| **候选耗尽** | 某条路线的全部基础可用候选被逐一拒绝 | 可作为"该组合下不可布通"的证据 |
| **只读审计** | 只比对与分析，不改变布局 | 只能作为机制解释与归因 |
| **离线沙箱** | 固定案例、独立入口复算，不写回正式状态 | 只能作为可行性证据 |

## 7.2 Top-U 主排序反转 A/B（完整布局实验）

基线的主排序键为 `(group, start.x, end.x, start.pmt_id, end.pmt_id, id)`，全部升序。实验只改一个变量：**group 0（Top-U）的主排序 x 取反（降序）**，次级 x、PMT ID、波导 ID 的平局次序不变，其余分组与网格全部不动。

结果：

| 指标 | 基线 | 反转后 | 变化 |
| --- | ---: | ---: | ---: |
| topU–topU 双交叉对 | 1903 | **0** | −1903 |
| 物理交点总数 | 55935 | 52129 | −3806 |
| 有交叉的路线对 | 49502 | 47599 | −1903 |
| 双交叉对总数 | 6433 | 4530 | −1903 |
| 全局 <20° 交叉 | 1508 | 984 | −524 |
| 全局平均交叉角 | 78.636° | 79.822° | +1.186° |
| **多波导交叉判据检出数** | 318 | **345** | **+27（+8.49%）** |

112 条 Top-U 的"路线—轨道映射"全部改变，但被占用的轨道索引集合（688..799）不变，非 Top-U 的每一条轨道分配与解析几何逐条相等（isolation 检查五项全 True）。由于嵌套端点对关系不随轨道分配改变，`1903 → 0` 在骨架层就已出现，说明改善发生在平滑之前。全局平均长度与已知非交叉损耗的均值/最大值都不变（138.3424 mm / 5.2646 dB），但个别 Top-U 长度被重分配（全局最短长度 31.8830 → 21.4330 mm）。

**同一实验同时给出反向证据：** 多波导交叉判据（三交点三角形至少两边 < 0.125 mm）的检出数由 318 **升到 345**，而 eligible 三角形集合完全不变（1,222,071）、boundary 仍为 2。**因此这不是全面改善。**

数据来源：`OpticalWaveguideRouter3D/outputs/step_8_5_top_u_order_ab_summary.json`；`docs/reports/step_8_5_top_u_order_ab_v01.md`。

## 7.3 多交叉差分审计（只读审计）

对 318 与 345 两个集合做 canonical 三元组比对：

| 项 | 数值 |
| --- | ---: |
| stable 三元组 | 204 |
| removed | 114 |
| added | 141 |
| 净变化 | +27 |
| 实际周转 | 255 个三元组（而非 27 个） |
| graph 三角形 | 2,063,548 → 1,835,220（移除 228,328、新增 0） |
| eligible 集合 | 1,222,071（完全不变） |

所有 added / removed 都含 Top-U，204 个 stable 全部不含。**机制是同一批 eligible 三元组内三个已存在的交点位置改变导致阈值进出，不是新生成了 eligible 资格。** 新增项也并非都卡在阈值边缘：141 个 added 中 87 个（61.7%）的第二短边余量大于 0.05 mm；但 added 含 <20° 交叉的 26 个，多于 removed 的 18 个。

数据来源：`OpticalWaveguideRouter3D/outputs/step_8_5_top_u_multi_crossing_delta_summary.json`；`docs/reports/step_8_5_top_u_multi_crossing_delta_v01.md`。

## 7.4 精确几何 guard 的负实验（有界中止 + 候选耗尽）

在 G0/G1 均固定 descend 的前提下做 guard 关闭/开启对照：每个候选生成真实 Line/Arc 临时几何，与已提交路径求精确交点，用**现有**判据判定，只有明确为 multi 才拒绝。

| 阶段 | 结果 | 证据等级 |
| --- | --- | --- |
| G0 gate（130,816 对） | **通过** | 完整 |
| 完整 G1 候选级诊断 | 成本过高，**本轮中止，未产生 G1 结论** | 有界中止 |
| 180 s 有界试运行 | routing 未完成；已提交普通路线 **217** 条（不是最终布通率）、已确认 guard 耗尽 **21**、候选尝试 14,914、明确 multi 拒绝 14,696 | 有界中止 |
| 最终审计判定 | **G1 FAILS ROUTABILITY REQUIREMENT** | 候选耗尽 |

关于 21 条失败的准确含义：它们**均已完成各自的全量扫描并拒绝了所有基础可用候选**（不是被 180 s 截断）；全部 14,384 次拒绝经独立重算 43,152 组 witness 对复核通过，交点与边长最大偏差约 2.8e-14 mm；事务重放对 4 条路线的占用、分配、几何、缓存、邻接五类 SHA-256 前后相等。其中 route 451 有 **756 个基础可用候选，全部被拒**；21 条中 top-U 14 条、top→bottom Z 7 条。

> **准确表述是：当前这一具体 greedy 硬 guard 组合（descend + exclusive 轨道 + R5 + 精确 multi 硬拒绝 + 无重布/回退）不能同时满足 multi 规避与 100% 普通路线可布通。这不扩展为"所有多交叉规避方案不可行"。**

关于性能：fast rejection 路径在固定小样本（40 条已提交路径、重复 30 次）上把中位耗时从 0.003903 s 降到 0.000528 s（约 7.39 倍）。**该倍率只对该 workload 成立，不是 512 全量的加速比**，pair kernel 约占 86.5% 的墙钟时间。

数据来源：`OpticalWaveguideRouter3D/outputs/step_8_5_exact_multi_guard_exhaustion_summary.json`、`step_8_5_exact_multi_guard_g0_gate.json`、`step_8_5_exact_multi_guard_fast_benchmark.json`；`docs/reports/step_8_5_exact_multi_guard_ab_v01.md`。

## 7.5 局部精确恢复：只有固定案例的离线沙箱验证

**先做归因（M1.5，只读）。** 把正式基线的 318 个 multi 全部归因（954 = 3 × 318 行，涉及 798 个唯一路线对）：**318/318 都涉及端点相连弯曲**，其中 265 个只含 LEFT 端弧、23 个只含 RIGHT 端弧、30 个混合；最常见的简单 signature 为 `Arc×H | Arc×V | H×V`，占 287/318（90.25%）。

**再做固定案例的离线沙箱验证（M1.6）。** 定义单 victim 精确恢复：移除一条普通路线，完整重算该 victim 的 511 个 pair 与含它的三元组，按 `(M_after, new_multi_created, |轨道位移|, 轨道索引)` 字典序取最优，且只接受整数 M 严格下降。

| 案例 | 扫描候选数 | 最小 M_after | 相对基线 318 | 结论 |
| --- | ---: | ---: | ---: | --- |
| M0011 | 347 | 318 | 0 | **无任何严格改进候选** |
| M0009 | 347 | 317 | −1 | 有改进 |
| M0001 | 347 | 316 | −2 | 有改进 |
| M0023 | 347 | 316 | −2 | 有改进 |

四个案例各扫描 347 个候选（346 个替代 + 1 个原位），共 1,388 个，几何全部合法。三次下降**各自从原 318 基线出发，不可相加，也不是"连续恢复后的 313"**。winner 经独立入口重算 511 个 star pair 与 37,128 / 4,371 / 5,995 个固定第三边，未做全 512 all-pairs 重跑。原位回放 4 例均为 M = 318、目标保留、delta 为空。

边界必须写明：

- 状态为 `FEASIBILITY_ONLY_NO_COMMIT`，**没有完成任何正式 recovery commit**；事务方案（版本检查 + 原子交换状态根）只被规定、未被实现；
- M0011 只能标 `FIRST_VICTIM_EXHAUSTED`，**不能标 `SINGLE_VICTIM_UNRECOVERABLE`**；
- 未尝试第二/第三 victim、未做 318 循环、未做深度 2 或递归；
- **设计文件（`step_8_5_m1_6_local_exact_recovery_design.md`）与检查点（`step_8_5_m1_6_checkpoint.md`）属于同一项工作，只计一个实验。**

> **不能把本章写成"已完成全部目标的恢复算法"。局部恢复只有固定案例的离线沙箱验证。**

数据来源：`OpticalWaveguideRouter3D/outputs/step_8_5_m1_5_multi_attribution_summary.json`、`step_8_5_m1_6_probe_summary.json`、`step_8_5_m1_6_independent_validation.json`、`step_8_5_m1_6_integrity.json`；`docs/reports/step_8_5_m1_5_exact_multi_attribution.md`、`step_8_5_m1_6_local_exact_recovery_design.md`、`step_8_5_m1_6_checkpoint.md`。

## 7.6 只读审计：原版优化逻辑的兼容性

两项只读审计没有产生可执行的算法改动，但给出了明确的"不实现"理由：

| 审计 | 结论 |
| --- | --- |
| 原版多交叉避让逻辑兼容性（K/M） | 论文 K 式中的 `d` 与 pitch、基础 D、K 的整数化与窗口边界、公式域外处理均未确认，因此**不实现"忠实原版 K"** |
| 层级/片段兼容性 | 片段语义与本报告基线 A 冲突（需把轨道占用从一对一改为一对多，会改变 A 的语义）；论文 4.1 已明确 PMT 间距 1.7 mm，但仍与实测纵向端点间距 1.875 mm、原点节距 4.5 mm 并存，**不能无歧义选定** |

**这两项都只是只读审计，不是优化实验。** 另外要记录一条口径事实：Step 8.5 全阶段的 `crossing_loss` 一直是 `NotImplementedError`、从未被调用，该阶段只有"已知传播 + 弯曲"估算。其 512 通道的已知非交叉损耗为：**454 条普通路线平均 5.4631 dB、最大 6.1874 dB；全部 512 条（含 58 条特殊 Z）平均 5.2646 dB。** 同一阶段把每个 90° 弯曲按论文印刷值 2.39 dB 计（每路两弯即 4.78 dB），而复现侧的弯曲损耗模型用的是原始密度 2.3826 dB —— 两者又有约 0.007 dB/弯的差异。

**因此该阶段的数字与含交叉近似的 5.5147 dB（512 R5）口径不同，不得并列比较，更不能当作完整链路损耗。**

数据来源：`OpticalWaveguideRouter3D/docs/reports/step_8_5_legacy_optimization_compatibility_audit.md`、`step_8_5_m_hierarchy_fragment_audit.md`、`step_8_5_loss_and_angle_v01.md`。

## 7.7 本章汇总表

| 实验 | 改变因素 | 规模 | 关键结果 | 证据等级 | 数据来源 |
| --- | --- | --- | --- | --- | --- |
| Top-U 主排序反转 A/B | Top-U 主排序 x 升序 → 降序 | 512（454 普通 + 58 特殊） | topU–topU 双交叉 1903 → 0；物理交点 −3806；**multi 318 → 345** | 完整布局实验 | `outputs/step_8_5_top_u_order_ab_summary.json` |
| 多交叉差分审计 | 无（只读比对） | 318 与 345 两个三元组集合 | stable 204 / removed 114 / added 141；eligible 不变 | 只读审计 | `outputs/step_8_5_top_u_multi_crossing_delta_summary.json` |
| exact multi guard A/B | guard 关/开（G0/G1 固定 descend） | G0 130,816 对；G1 未完成 | 180 s 上限触发；已提交 217、耗尽 21 | **有界中止 + 候选耗尽** | `outputs/step_8_5_exact_multi_guard_exhaustion_summary.json` |
| 多交叉归因 M1.5 | 无（只读归因） | 318 个 multi / 798 路线对 | 318/318 涉及端点相连弯曲 | 只读审计 | `outputs/step_8_5_m1_5_multi_attribution_summary.json` |
| 局部精确恢复探针 M1.6 | victim 轨道位置 | 4 案例 × 347 候选（离线） | 318 → 317 / 316 / 316；M0011 无改进 | **离线沙箱，未 commit** | `outputs/step_8_5_m1_6_probe_summary.json` |
| 原版优化兼容性 K/M | 无（只读） | 论文式与快照 | d/pitch、D、整数化、域外处理未确认 | 只读审计 | `docs/reports/step_8_5_legacy_optimization_compatibility_audit.md` |
| 层级/片段审计 | 无（只读） | 片段语义 vs 基线 A | 与本报告基线冲突，不可直接实现 | 只读审计 | `docs/reports/step_8_5_m_hierarchy_fragment_audit.md` |

| 负结果 / 未完成项 | 事实 | 数据来源 |
| --- | --- | --- |
| 排序反转不是全面改善 | multi 检出 318 → 345（+27）；added 141 中含 26 个 <20° 交叉 | `step_8_5_top_u_multi_crossing_delta_v01.md` |
| 硬 guard 不可布通 | G1 FAILS ROUTABILITY；21 条真实候选耗尽；route 451 的 756 个候选全被拒 | `step_8_5_exact_multi_guard_ab_v01.md` |
| guard 全量实验未完成 | 完整 G1 被中止，最终指标记为"不适用——布线未完成" | `step_8_5_exact_multi_guard_exhaustion_summary.json` |
| 加速比被限定 | 7.39 倍仅来自 40 条路径的固定小样本，非 512 全量加速比 | `step_8_5_exact_multi_guard_ab_v01.md` |
| 恢复未落地 | 无 commit；4 案例不可相加；M0011 仅为"第一 victim 耗尽" | `step_8_5_m1_6_checkpoint.md` |
| 原版 K 不可实现 | `d`/pitch、基础 D、整数化、域外处理均未确认 | `step_8_5_legacy_optimization_compatibility_audit.md` |
| 片段语义与基线冲突 | 需把轨道占用改为一对多，改变基线 A 的语义 | `step_8_5_m_hierarchy_fragment_audit.md` |
| 该阶段无交叉损耗 | `crossing_loss` 全程 `NotImplementedError`，只有传播 + 弯曲估算 | `step_8_5_loss_and_angle_v01.md` |
| 设计文件与检查点重复计数风险 | 同一项工作，只计一个实验 | `step_8_5_m1_6_local_exact_recovery_design.md`、`step_8_5_m1_6_checkpoint.md` |
