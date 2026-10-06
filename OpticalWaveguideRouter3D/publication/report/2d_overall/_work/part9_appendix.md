<!-- pagebreak -->
# 附录 A　二维实验总表

本表把本报告覆盖的全部二维实验按"研究问题"列出。**证据等级**只描述实验完成度；"限制"列给出该实验不能被怎样使用。3D 的三维抬层实验列在最后一行，仅用于说明范围外内容，不计入二维验证。

| 实验问题 | 输入 | 改变因素 | 冻结条件 | 结果 | 限制 | 数据来源 |
| --- | --- | --- | --- | --- | --- | --- |
| 能否复现原程序的几何与轨道 | 512 连接表 + 2020 端点快照 | 无（重建） | 原运行时 Python 3.8.10 | 输入/轨道/弯曲参数/GDS 512/512 与字节码一致 | 256 无原版参照 | `OpticalWaveguideRouter2D/docs/exact_legacy_fidelity_report.md` |
| 能否复现原报告的损耗 | 256 R5、512 R5、512 R4 | 无 | 同一损耗模型 | 六个数字落在一位小数精度内（最大相对误差 1.05%） | 交叉项为数字化近似 | `publication/tables/t32_reproduction_compare_data.csv` |
| 半径对损耗的影响（复现侧） | 512 连接表 | 半径 2/3/4/5 mm，各自独立布线 | 板面、线宽、间距不变 | 平均 16.5873 → 5.5147 dB | 只有 512；R2–R4 无几何风险统计 | `publication/tables/t33_radius_sweep_512_data.csv` |
| 统一 R6 是否优于原版 R5 | 256/512 真实输入 | 半径 5 → 6 mm 并重新布线 | 同一评价器 | −0.9426 dB（256）/ −0.9579 dB（512） | 512 有 2 条未布通 | `outputs/opt2d/{256,512}/comparison.csv` |
| 只搜索候选轨道值多少 | 同上 | 取首个可用 → 枚举并评分 | 半径固定 R5 | −0.0014 / −0.0016 dB（约 −0.03%） | 收益上限只有交叉项占比 | 同上 |
| 自适应 R5/R6 值多少 | 同上 | 半径并入候选 | 同上 | 512 恢复 512/512，代价 +0.0029 dB | 收益是可布通性而非损耗 | `outputs/opt2d/{256,512}/sensitivity.json` |
| 候选数、顺序、正则、拆线是否有效 | 同上 | K / 顺序 / penalty / refine | 同上 | K 饱和；顺序与 penalty=0 大量未布通；拆线 0 接受 | 未布通配置均值不可比 | `publication/tables/t52_step12_ablation_data.csv` |
| 固定端点后各方案是否仍成立 | 冻结端点（方案 A 的 `sx/sy/lx/ly`） | 端点冻结 + 六方案 | 端点冻结、端口槽位交换关闭 | 全部方案端点变化 0、256/256 与 512/512 | 半径未冻结 | `outputs/opt2d_step13_fix/{256,512}/comparison.csv` |
| 自由弯角 S 形值多少 | 同上 | U 型 → 自由弯角（F5/F56） | 端点冻结 | −2.3089 dB（256）/ −2.2220 dB（512） | 交叉与间距违规大幅上升 | `publication/tables/t61_step13_main_data.csv` |
| 求交修复是否改变结论 | 旧产物几何 | 稳健直线分类 + 重布 | 端点冻结 | 256 F56 重合 1 → 0，平均 +0.0014 dB；512 零变化 | 旧的"无重合"结论已撤回 | `outputs/opt2d_step13_fix/legacy_scheme_scan.csv` |
| 受约束配置是否有效（半径未冻结） | 同上 | 间距 / 小角惩罚 | 端点冻结，**半径自适应** | small 把 <20° 由 657 降到 434（256） | **混入半径选择影响，不可与冻结结果比较** | `outputs/opt2d_step13_constrained/{256,512}/constrained_comparison.csv` |
| 冻结半径后的公平对照 | F56 逐路半径 | 六配置 base/spacing/small/touch/both/opt_base | **端点 + 逐路半径冻结 + 固定保护集合** | base 与未冻结 F56 逐项相同；256 三约束 ≤ +0.03 dB | 512 的 spacing/both 伤害保护路线 | `publication/tables/t71_step14_main_data.csv` |
| 约束能否降低尾部风险 | 同上 | 三种约束 | 同上 | ×10 情景下 small 把最大压低 0.7749 / 0.9504 dB | ×1/×2/×5/×10 是人为情景 | `publication/tables/t74_step14_sensitivity_data.csv` |
| 保护性局部优化能走多远 | base 布局 | 逐条移除 + 重布 + 完整评价 | 冻结 + 保护集合 + 验收规则 | 512 接受 6 条（×5 情景 −0.0924 dB）；**256 零接受** | 512 的 ×10 情景未改善 | `publication/tables/t73_step14_optimize_data.csv` |
| Top-U 主排序反转 | 512 原版布局 | Top-U 主排序 x 反序 | 其余分组与网格不变 | 双交叉 1903 → 0；multi 318 → 345 | **不是全面改善** | `outputs/step_8_5_top_u_order_ab_summary.json` |
| 多交叉差分归因 | 318 与 345 三元组 | 无（只读比对） | — | stable 204 / removed 114 / added 141；eligible 不变 | 只读审计 | `outputs/step_8_5_top_u_multi_crossing_delta_summary.json` |
| 精确几何 guard 能否可行 | 512 | guard 关/开 | G0/G1 固定 descend | G0 通过；G1 **中止**，21 条候选耗尽 | 有界中止 + 候选耗尽，不可当完整布局结果 | `outputs/step_8_5_exact_multi_guard_exhaustion_summary.json` |
| 局部精确恢复是否可行 | 4 个固定案例 | victim 轨道位置 | 离线沙箱 | 318 → 317 / 316 / 316；M0011 无改进 | **未 commit；4 例不可相加** | `outputs/step_8_5_m1_6_probe_summary.json` |
| 原版多交叉逻辑能否照搬 | 论文式与快照 | 无（只读） | — | 关键参数未确认，**不实现** | 只读审计 | `docs/reports/step_8_5_legacy_optimization_compatibility_audit.md` |
| （范围外）三维局部抬层 | 512 与**合成** 1024 | 层数 / 抬层 | — | 近距路线对 204,291 → 138,113（−32.39%） | 合成输入、无三维光学损耗、未无碰撞 | `publication/tables/t81_3d_experiments_data.csv` |

<!-- pagebreak -->
# 附录 B　实验资料索引

## B.1 二维优化主线（按阶段）

| 资料 | 内容 | 引用注意 |
| --- | --- | --- |
| `OpticalWaveguideRouter3D/docs/reports/step_12_opt2d_2d_routing_optimization.md` | 统一评价器、A/B/C/D、消融与失败案例 | 端点未冻结，**不可与 Step 13 及之后混用** |
| `OpticalWaveguideRouter3D/docs/reports/step_13_opt2d_fixed_endpoints_and_freeform.md` | 固定端点与自由弯角 S 形 | **部分结论已勘误**，作为方法与历史记录阅读 |
| `OpticalWaveguideRouter3D/docs/reports/step_13_opt2d_fix_and_reverification.md` | 真实重合误判修复、重新布线、口径更正 | **优先采用**；其 §1.3 的"18 项"应为 19 项 |
| `OpticalWaveguideRouter3D/docs/reports/step_14_opt2d_frozen_robust_optimization.md` | 冻结对照、压力情景、保护性局部优化、统计口径统一 | 最新阶段；其 §3.2 的"逐项一致"无法由产物核实 |
| `OpticalWaveguideRouter3D/docs/2d_routing/experiment_reports_index.md` | 完整索引 | 索引本身不是实验结果 |
| `OpticalWaveguideRouter3D/docs/2d_routing/parameters_and_ports.md` | 参数、损耗与端口排布说明 | 其"256 没有逐路线损耗分析"的表述**已被后续复现工作取代**（见 `OpticalWaveguideRouter2D/results/fiberBoard256_loss.xlsx`） |

## B.2 二维原程序复现与诊断

| 资料 | 内容 |
| --- | --- |
| `OpticalWaveguideRouter2D/docs/migration_report.md` | 迁移与复现过程；**其轨道使用数（243/475）与产物不符，本报告以产物 245/477 为准** |
| `OpticalWaveguideRouter2D/docs/exact_legacy_fidelity_report.md` | 与原可执行程序字节码的逐阶段对照 |
| `OpticalWaveguideRouter2D/docs/loss_model_reconstruction_report.md` | 损耗模型复刻、交叉表缺失证据、三口径敏感性 |
| `OpticalWaveguideRouter2D/docs/debug_first_divergence.md` | 第一处分歧的定位；区分旧图与原程序 |

## B.3 早期二维阶段资料（Step 8 / 8.5，27 份）

| 分组 | 文件 | 性质 |
| --- | --- | --- |
| 输入、端点与轨道 | `step_8_legacy_input_validation.md`、`step_8_legacy_layout_audit.md`、`step_8_legacy_512_snapshot.md`、`step_8_legacy_track_assignment_audit.md`、`step_8_track_policy_candidates.md` | 审计与候选方案（后者标题注明待人工选择） |
| 路线构造与碰撞 | `step_8_legacy_512_route_preparation.md`、`step_8_legacy_512_track_assignment_v01.md`、`step_8_legacy_512_routes_v01.md`、`step_8_legacy_512_collision_validation_v01.md`、`step_8_5_legacy_512_smoothing_v01.md`、`step_8_5_special_z_arc_architecture.md`、`step_8_5_special_z_v01.md`、`step_8_5_exact_curve_collision_v01.md`、`step_8_5_legacy_512_exact_validation_v01.md` | 实验记录 |
| 交叉、损耗、排序与防护 | `step_8_5_route_level_intersections_v01.md`、`step_8_5_multi_waveguide_crossing_v01.md`、`step_8_5_double_cross_audit_v01.md`、`step_8_5_loss_and_angle_v01.md`、`step_8_5_top_u_order_ab_v01.md`、`step_8_5_top_u_multi_crossing_delta_v01.md`、`step_8_5_legacy_optimization_compatibility_audit.md`、`step_8_5_exact_multi_guard_ab_v01.md` | 实验与负结果；`loss_and_angle` 阶段**无交叉损耗** |
| 层级、归因与局部恢复 | `step_8_5_m_hierarchy_fragment_audit.md`、`step_8_5_m1_dynamic_d_diagnostic.md`、`step_8_5_m1_5_exact_multi_attribution.md`、`step_8_5_m1_6_local_exact_recovery_design.md`、`step_8_5_m1_6_checkpoint.md` | **设计文件与检查点为同一项工作，只计一个实验** |

## B.4 汇总入口

| 资料 | 说明 |
| --- | --- |
| `OpticalWaveguideRouter3D/publication/report/实验结果简明说明.md` | 文字总览；前五项为二维，第六项为三维 |
| `OpticalWaveguideRouter3D/publication/tables/` | t31–t34（复现）、t51–t52（Step 12）、t61–t64（Step 13）、t71–t74（Step 14）、t81（三维） |
| `OpticalWaveguideRouter3D/publication/figures/` | 35 张已审查图（PDF/SVG/PNG 三格式） |
| `OpticalWaveguideRouter3D/publication/manifest/` | `figure_sources.csv`、`figure_coverage.csv`、`experiment_inventory.csv`、`quality_review.md` |

<!-- pagebreak -->
# 附录 C　表格与图—原始数据对应关系

## C.1 正文表格

| 报告表 | 内容 | 原始数据 |
| --- | --- | --- |
| 表（1.1 节） | 端口规模与连接输入 | `OpticalWaveguideRouter3D/docs/2d_routing/parameters_and_ports.md`；`step_8_legacy_input_validation.md` |
| 表（1.2 节） | 端点坐标公式 | `step_8_legacy_layout_audit.md`、`step_8_legacy_512_snapshot.md` |
| 表（1.3 节） | 板面、线宽、间距、半径 | `parameters_and_ports.md`；`results/fiberBoard{256,512}bend.xlsx`（轨道范围实测） |
| 表（1.4 节） | 损耗模型与口径 | `loss_model_reconstruction_report.md`；`publication/tables/t34_crossing_model_sensitivity_data.csv` |
| 表（1.5 节） | 编号与术语 | `实验结果简明说明.md`；`step_12`、`step_13` 报告 |
| 表（2.2 节） | 对照层级 | `exact_legacy_fidelity_report.md`、`debug_first_divergence.md` |
| 表（2.3 节） | 复现损耗与原报告 | `results/fiberBoard{256,512}_loss_summary.json`、`fiberBoard512_loss_R4_summary.json`；`t32` |
| 表（2.4.1 节） | 弯曲损耗表 3-1 复算 | `OpticalWaveguideRouter2D/loss_model.py`；`t31_bend_model_thesis_vs_repro_data.csv` |
| 表（2.4.2 节） | 交叉损耗三口径 | `t34_crossing_model_sensitivity_data.csv` |
| 表（3.1 节） | 半径扫描 | `publication/tables/t33_radius_sweep_512_data.csv` |
| 表（3.2 节） | 候选轨道与自适应半径比较 | `outputs/opt2d/{256,512}/comparison.csv`；`t51_step12_main_data.csv` |
| 表（3.3 节） | Step 12 消融 | `outputs/opt2d/{256,512}/sensitivity.json`；`t52_step12_ablation_data.csv` |
| 表（3.4 节） | 统一 R6 与自适应半径 | `outputs/opt2d/{256,512}/sensitivity.json` |
| 表（3.5 节） | 参数收益与算法收益拆解 | `outputs/opt2d/{256,512}/comparison.csv` |
| 表（4.3 节） | 固定端点与自由弯角主结果 | `outputs/opt2d_step13_fix/{256,512}/comparison.csv`；`t61`、`t62` |
| 表（4.4 节） | 收益与代价 | `outputs/opt2d_step13_fix/{256,512}/comparison.csv`、`acceptance.json` |
| 表（4.5 节） | 最差链路追踪 | `outputs/opt2d_step13/{256,512}/worst_route_tracking.csv`；`outputs/opt2d_step14/{256,512}/base/protection_routes.csv` |
| 表（4.6 节） | 交叉表风险稳健性 | `outputs/opt2d_step13_fix/{256,512}/sensitivity.csv`；`t64` |
| 表（5.1 节） | 求交修复判据 | `docs/reports/step_13_opt2d_fix_and_reverification.md`；`OpticalWaveguideRouter3D/tests/test_opt2d_step13_fixes.py` |
| 表（5.2 节） | 事件层级定义 | `src/opt2d/intersections.py`、`spacing.py`、`evaluator.py` |
| 表（5.2.1 节） | 段级接触 vs 物理接触 | `outputs/opt2d_step14/{256,512}/comparison.csv`；`step_13_fix/legacy_scheme_scan.csv` |
| 表（5.3 节） | 旧产物合法性扫描 | `outputs/opt2d_step13_fix/legacy_scheme_scan.csv` |
| 表（5.3.1 节） | 修复代价与逐路变化 | `outputs/opt2d_step13_fix/{256,512}/comparison.csv`、`per_route_delta.csv` |
| 表（5.4 节） | 已更正的旧结论清单 | 本节各"证据"列 |
| 表（5.5 节） | 口径如何改变结论 | 本节各"来源"列 |
| 表（6.1 节） | 冻结依据与保护集合 | `outputs/opt2d_step14/{256,512}/protection_set.json`、`radius_freeze_check.csv` |
| 表（6.2 节） | 冻结约束与保护性优化 | `outputs/opt2d_step14/{256,512}/comparison.csv`、`acceptance.csv`、`references.csv`；`t71` |
| 表（6.3 节） | 保护路线逐路变化与裕度 | `outputs/opt2d_step14/{256,512}/{scheme}/protection_routes.csv`、`protection_margins.csv` |
| 表（6.4 节） | 压力情景比较 | `outputs/opt2d_step14/{256,512}/sensitivity.csv`；`t74` |
| 表（6.5 节） | 保护性局部优化记录 | `outputs/opt2d_step14/{256,512}/optimize_record.json`、`optimize_attempts_base.csv`、`probe/probe_summary.csv`；`t73` |
| 表（7.2–7.7 节） | 排序、guard 与局部恢复 | `outputs/step_8_5_*.json`（见各节来源） |
| 附录 A | 二维实验总表 | 各"数据来源"列 |

## C.2 正文插图

| 图 | 文件 | 原始数据 |
| --- | --- | --- |
| 交叉模型三口径 | `publication/figures/f310_crossing_model_sensitivity.png` | `OpticalWaveguideRouter2D/data/crossing_loss_from_thesis_fig3_12.csv`、`results/fiberBoard512_loss.xlsx` |
| 256 / 512 复现布局 | `OpticalWaveguideRouter2D/results/fiberBoard{256,512}bend.png` | 复现产物（`results/fiberBoard{256,512}bend.xlsx` 与 GDS） |
| 复现精度对照 | `publication/figures/f32_reproduction_accuracy.png` | `results/fiberBoard*_loss_summary.json` |
| 字节码逐路对照 | `publication/figures/f39_legacy_bytecode_check.png` | `OpticalWaveguideRouter2D/scratch/legacy_loss/legacy*.json` |
| 交叉角分布 | `publication/figures/f37_crossing_angle_distribution.png` | `results/fiberBoard{256,512}_loss.xlsx` |
| 半径扫描 | `publication/figures/f33_radius_sweep_512.png` | `results/fiberBoard512_loss_R{2,3,4}_summary.json` |
| Step 12 主结果 / 分解 / 消融 / 效率 | `publication/figures/f5{1,2,3,4}_*.png` | `outputs/opt2d/{256,512}/comparison.csv`、`sensitivity.json` |
| Step 13 主结果 / 分解 / 最差路线 / 补修 / 受约束 / 敏感性 | `publication/figures/f6{1,2,3,4,5,6,7}_*.png` | `outputs/opt2d_step13_fix/{256,512}/*`、`outputs/opt2d_step13_constrained/*` |
| Step 14 主结果 / 情景 / 小角 / 保护 / 优化 / 探针 / 敏感性 | `publication/figures/f7{1,2,3,4,5,6,7}_*.png` | `outputs/opt2d_step14/{256,512}/*` |

## C.3 图表复用与重绘说明

- 本报告的插图**全部复用** `OpticalWaveguideRouter3D/publication/figures/` 下已通过质量审查的 35 张图（400 dpi PNG），以及 `OpticalWaveguideRouter2D/results/` 的复现布局图；**没有重新运行任何实验或绘图脚本**。
- 图与表的生成来源、字段、筛选条件记录在 `publication/manifest/figure_sources.csv` 与 `figure_coverage.csv`。
- 每张图在正文中的题注都写明规模、方案与统计口径；不同端点、半径、评价器或损耗口径的数据没有放进同一个公平比较。

<!-- pagebreak -->
# 附录 D　阅读提示与口径速查

- **全部损耗都是现有损耗模型的计算值，不是器件实测值。**
- **平均、最大、P95 描述的是一次布局内各条路线的统计，不是重复实验统计。**
- **运行时间若只有一次记录，只描述该次实测，不能宣称普遍效率优势。**
- **×1/×2/×5/×10 是人为压力情景，不是实测误差范围。**
- **间距阈值（线宽 + 标称间隔：256 为 0.30 mm、512 为 0.175 mm）是实验假设，不代表制造规范。**
- **"交叉事件数"必须注明是"全网唯一事件"还是"逐路累计"**，两者恒有 2 倍关系。
- **"接触"必须注明是"解析段级"还是"按整条路线合并后的物理事件"**；本项目两规模的物理接触均为 0。
- **R5 / R6 是半径（mm）；实验清单编号 R05 / R06 是另一套编号。**
- **本报告只覆盖二维；三维内容仅见 8.6 节，不进入任何二维结果表。**
- 本报告只整理与核查已有产物，**未修改任何路由代码、输入、实验参数或历史记录，也未重新运行优化**。

配套文件：`数据来源与口径核查清单.md`（逐项列出每个关键数字的来源文件、统计口径、核查结论与更正记录）。
