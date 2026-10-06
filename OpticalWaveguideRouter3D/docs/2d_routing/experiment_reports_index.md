# 二维实验报告与相关资料索引

核对日期：2026-10-05。本索引列出两个项目目录中的报告原件，不迁移或覆盖任何历史文件。主线优化报告为 4 份，另有 27 份 Step 8/8.5 阶段记录及 4 份二维复现/诊断文档。审计、方案和检查点不等同于独立完成的优化实验。

## 1. 二维优化主线（建议按顺序阅读）

| 报告 | 内容与引用注意 |
| --- | --- |
| [Step 12：二维布线优化实验](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_12_opt2d_2d_routing_optimization.md>) | 原版对照、统一 R6、候选轨道、局部自适应 R5/R6、消融与失败案例。 |
| [Step 13：固定端点与自由弯角 S 形路径](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_13_opt2d_fixed_endpoints_and_freeform.md>) | 固定端点、U 型与自由弯角 F5/F56；部分结论已勘误，作为方法和历史记录阅读。 |
| [Step 13 补修与复验](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_13_opt2d_fix_and_reverification.md>) | 真实重合误判修复、重新布线、间距检查与旧结果口径更正；优先采用补修数据。 |
| [Step 14：冻结对照下的二维稳健优化](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_14_opt2d_frozen_robust_optimization.md>) | 冻结逐路半径和保护集合，比较小角/间距约束、压力情景、保护性局部重布，统一物理接触统计。 |

## 2. 二维原程序复现与诊断

以下文件位于 OpticalWaveguideRouter2D/docs/。

| 文档 | 内容 |
| --- | --- |
| [迁移与复现报告](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter2D/docs/migration_report.md>) | 旧 AutoRouter 到 Python 3.10 项目的恢复、迁移和验证。 |
| [原版几何一致性报告](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter2D/docs/exact_legacy_fidelity_report.md>) | 输入快照、轨道、圆弧及 GDS 输出与原字节码的逐阶段对照。 |
| [原版损耗模型复刻报告](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter2D/docs/loss_model_reconstruction_report.md>) | 传播、弯曲、交叉损耗模型与复现结果，参数来源及局限。 |
| [首次分歧诊断](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter2D/docs/debug_first_divergence.md>) | 轨道选择追踪，区分旧图与原可执行程序的差异。 |

## 3. 早期二维阶段资料（27 份）

这些文件位于 OpticalWaveguideRouter3D/docs/reports/。

### 输入、端点布局与轨道规则

| 文件 | 主题/性质 |
| --- | --- |
| [step_8_legacy_input_validation.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_legacy_input_validation.md>) | 输入验证 |
| [step_8_legacy_layout_audit.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_legacy_layout_audit.md>) | 布局来源审计 |
| [step_8_legacy_512_snapshot.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_legacy_512_snapshot.md>) | 512 端点快照验证 |
| [step_8_legacy_track_assignment_audit.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_legacy_track_assignment_audit.md>) | 原轨道分配规则审计 |
| [step_8_track_policy_candidates.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_track_policy_candidates.md>) | 轨道策略候选方案；标题注明待人工选择 |

### 路线构造、解析几何与碰撞验证

| 文件 | 主题/性质 |
| --- | --- |
| [step_8_legacy_512_route_preparation.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_legacy_512_route_preparation.md>) | 512 路由准备记录 |
| [step_8_legacy_512_track_assignment_v01.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_legacy_512_track_assignment_v01.md>) | 512 轨道分配实验 |
| [step_8_legacy_512_routes_v01.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_legacy_512_routes_v01.md>) | 512 路线生成记录 |
| [step_8_legacy_512_collision_validation_v01.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_legacy_512_collision_validation_v01.md>) | 早期全局碰撞验证 |
| [step_8_5_legacy_512_smoothing_v01.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_5_legacy_512_smoothing_v01.md>) | 普通路线 Line/Arc 平滑 |
| [step_8_5_special_z_arc_architecture.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_5_special_z_arc_architecture.md>) | 特殊 Z 与圆弧表示方案审计 |
| [step_8_5_special_z_v01.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_5_special_z_v01.md>) | 受限特殊 Z 双圆弧模型 |
| [step_8_5_exact_curve_collision_v01.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_5_exact_curve_collision_v01.md>) | 精确 Line/Arc 求交与碰撞检测 |
| [step_8_5_legacy_512_exact_validation_v01.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_5_legacy_512_exact_validation_v01.md>) | 512 解析曲线全局验证 |

### 交叉、损耗、排序与防护

| 文件 | 主题/性质 |
| --- | --- |
| [step_8_5_route_level_intersections_v01.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_5_route_level_intersections_v01.md>) | 路线级物理交叉事件归并 |
| [step_8_5_multi_waveguide_crossing_v01.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_5_multi_waveguide_crossing_v01.md>) | 多波导交叉检测 |
| [step_8_5_double_cross_audit_v01.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_5_double_cross_audit_v01.md>) | 双交叉路线对拓扑审计 |
| [step_8_5_loss_and_angle_v01.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_5_loss_and_angle_v01.md>) | 已知传播/弯曲损耗与交叉角；该阶段未计算可信交叉损耗 |
| [step_8_5_top_u_order_ab_v01.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_5_top_u_order_ab_v01.md>) | Top-U 主排序反转 A/B 实验 |
| [step_8_5_top_u_multi_crossing_delta_v01.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_5_top_u_multi_crossing_delta_v01.md>) | 排序变化下的多交叉差分审计 |
| [step_8_5_legacy_optimization_compatibility_audit.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_5_legacy_optimization_compatibility_audit.md>) | 原多交叉避让逻辑兼容性审计 |
| [step_8_5_exact_multi_guard_ab_v01.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_5_exact_multi_guard_ab_v01.md>) | 精确几何多交叉 guard 对照；正文标题 V0.2，含可布通性失败与中止结果，非完整 G1 布局 |

### 层级、归因与局部恢复

| 文件 | 主题/性质 |
| --- | --- |
| [step_8_5_m_hierarchy_fragment_audit.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_5_m_hierarchy_fragment_audit.md>) | 层级/片段兼容性与规则推导审计 |
| [step_8_5_m1_dynamic_d_diagnostic.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_5_m1_dynamic_d_diagnostic.md>) | 只读 Dynamic-D 与层级诊断 |
| [step_8_5_m1_5_exact_multi_attribution.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_5_m1_5_exact_multi_attribution.md>) | 多交叉空间/路线段归因审计 |
| [step_8_5_m1_6_local_exact_recovery_design.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_5_m1_6_local_exact_recovery_design.md>) | 局部精确恢复设计与可行性；含固定案例离线沙箱验证，未完成正式 recovery commit |
| [step_8_5_m1_6_checkpoint.md](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/reports/step_8_5_m1_6_checkpoint.md>) | 同一局部恢复工作的检查点，不能重复计为新实验 |

## 4. 汇总交付与简明入口

下列汇总同时包含二维和三维内容，不是独立的纯二维 PDF。

| 文件 | 用途 |
| --- | --- |
| [光波导布线全部实验报告.pdf](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/publication/report/光波导布线全部实验报告.pdf>) | 全部已执行实验的汇总，包括二维复现、半径、路径结构、风险保护及早期诊断。 |
| [光波导自动布线算法实验报告.pdf](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/publication/report/光波导自动布线算法实验报告.pdf>) | 按论文结构组织的完整报告。 |
| [光波导自动布线算法实验报告.docx](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/publication/report/光波导自动布线算法实验报告.docx>) | 上述完整报告的可编辑 Word 来源。 |
| [实验结果简明说明](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/publication/report/实验结果简明说明.md>) | 文字总览，前五项为二维复现与优化，第六项为三维扩展。 |

补充入口：[二维参数、损耗与端口排布说明](<C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter3D/docs/2d_routing/parameters_and_ports.md>)。这是参数状态和资料说明，不单独计为优化实验报告。

当前二维优化主线的最新阶段是 Step 14。引用 Step 13 时同时查看补修版；历史模型、统计口径及不同几何/半径条件的数字不能直接混用。
