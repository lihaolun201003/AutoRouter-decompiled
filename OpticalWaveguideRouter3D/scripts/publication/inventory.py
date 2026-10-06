"""实验清单、图/表覆盖表与来源台账。

输出到 publication/manifest/：
* experiment_inventory.csv —— 全部实际存在的实验配置（含数据文件与状态）；
* figure_coverage.csv —— 每张图的覆盖实验、源文件与输出；
* table_coverage.csv —— 每张表的覆盖实验、源文件与输出。

本模块只做登记与校验（文件存在性、覆盖闭合性），不读取实验数值。
"""

from __future__ import annotations

from pathlib import Path

import pubstyle as S

MANIFEST = S.MANIFEST_DIR
OUT_FIG = "publication/figures"
OUT_TAB = "publication/tables"

# ---------------------------------------------------------------------------
# 实验清单
# ---------------------------------------------------------------------------
# status: 有效 / 历史（含历史非法几何） / 诊断（非任务口径） / 验证（基础步） / 参照 / 核对
EXPERIMENTS = [
    # ---- 论文复现 ----
    dict(id="R01", group="论文复现", name="论文表 3-1 弯曲损耗模型对照",
         scale="256/512", config="弯曲模型（R=2/3/4/5/6 mm）",
         description="论文印刷值与复刻模型的 90° 弯曲损耗对照",
         data_files=["OpticalWaveguideRouter2D/loss_model.py（BEND_TABLE 复算）",
                     "论文表 3-1（引用记录）"],
         metrics="bend_loss_90_db", figures="f31", tables="t31", status="有效",
         notes="几何离散点：R=2/3/4/5/6 mm；复刻由 tl/ll 表推得密度。"),
    dict(id="R02", group="论文复现", name="256 通道 R5 复现",
         scale="256", config="原版 R5 几何",
         description="论文 4.2 节 256 通道的复现（平均 5.2788 / 最大 6.3330 dB vs 论文 5.3 / 6.4）",
         data_files=["OpticalWaveguideRouter2D/results/fiberBoard256_loss.xlsx",
                     "OpticalWaveguideRouter2D/results/fiberBoard256_loss_summary.json"],
         metrics="mean/max/p95_loss_db、crossing_angles、total_length",
         figures="f32;f34;f35;f36;f37;f39", tables="t32", status="有效",
         notes="布通率 100%（全部 256 条布通）。"),
    dict(id="R03", group="论文复现", name="512 通道 R5 复现",
         scale="512", config="原版 R5 几何",
         description="论文 4.1 节 512 通道的复现（平均 5.5147 / 最大 6.5761 dB vs 论文 5.5 / 6.6）",
         data_files=["OpticalWaveguideRouter2D/results/fiberBoard512_loss.xlsx",
                     "OpticalWaveguideRouter2D/results/fiberBoard512_loss_summary.json"],
         metrics="mean/max/p95_loss_db、crossing_angles、total_length",
         figures="f32;f34;f35;f36;f37;f39", tables="t32", status="有效",
         notes="布通率 100%；最小交叉角 14°（论文记录值一致）。"),
    dict(id="R04", group="论文复现", name="512 通道 R4 复现",
         scale="512", config="R4 几何（论文 4.3 对照）",
         description="论文 4.3 节 R=4 mm 的复现（9.8096 / 10.9815 dB vs 论文 9.8 / 11.0）",
         data_files=["OpticalWaveguideRouter2D/results/fiberBoard512_loss_R4.xlsx",
                     "OpticalWaveguideRouter2D/results/fiberBoard512_loss_R4_summary.json"],
         metrics="mean/max_loss_db", figures="f32;f33;f34;f39", tables="t32;t33",
         status="有效", notes="论文 R4 含 100% 布通率记录；复现同样全部布通。"),
    dict(id="R05", group="论文复现", name="512 通道 R2 半径扫描",
         scale="512", config="R2 几何",
         description="半径扫描点：平均 16.5873 / 最大 17.7056 dB",
         data_files=["OpticalWaveguideRouter2D/results/fiberBoard512_loss_R2.xlsx",
                     "OpticalWaveguideRouter2D/results/fiberBoard512_loss_R2_summary.json"],
         metrics="mean/max_loss_db、bend share", figures="f33;f34;f39", tables="t33",
         status="有效", notes="论文未印 R2 数值（论文只印 R4）。"),
    dict(id="R06", group="论文复现", name="512 通道 R3 半径扫描",
         scale="512", config="R3 几何",
         description="半径扫描点：平均 14.2260 / 最大 15.4284 dB",
         data_files=["OpticalWaveguideRouter2D/results/fiberBoard512_loss_R3.xlsx",
                     "OpticalWaveguideRouter2D/results/fiberBoard512_loss_R3_summary.json"],
         metrics="mean/max_loss_db、bend share", figures="f33;f34;f39", tables="t33",
         status="有效", notes="论文未印 R3 数值。"),
    dict(id="R07", group="论文复现", name="交叉损耗模型敏感性（三种口径）",
         scale="512", config="A 全 90°/ B 图 3-12 锚定（主口径）/ C 图 3-12 原始值",
         description="固定几何复算：均值 5.4758 / 5.5147 / 5.5745 dB",
         data_files=["OpticalWaveguideRouter2D/data/crossing_loss_from_thesis_fig3_12.csv",
                     "OpticalWaveguideRouter2D/results/fiberBoard512_loss.xlsx"],
         metrics="mean/max_loss_db（三口径）", figures="f310", tables="t34",
         status="有效", notes="数值由本次分析复算，与 loss_model_reconstruction_report.md 第 7 节记录一致。"),
    dict(id="R08", group="论文复现", name="legacy 512 精确几何审计（step 8.5）",
         scale="512", config="物理求交口径",
         description="对原版平滑几何精确求交：55935 事件、49502 交叉对、最小角 2.84°",
         data_files=["OpticalWaveguideRouter3D/outputs/step_8_5_legacy_512_physical_summary.json",
                     "OpticalWaveguideRouter3D/outputs/step_8_5_legacy_512_multi_crossing_summary.json",
                     "OpticalWaveguideRouter3D/outputs/step_8_5_legacy_512_loss_summary.json"],
         metrics="cross_events、cross_pairs、multiplicity、crossing_angles",
         figures="f38", tables="--", status="有效",
         notes="物理口径与复现表整数度逐路口径不同，两者分开呈现。"),
    dict(id="R09", group="论文复现", name="原版字节码逐路对照（占位交叉表）",
         scale="256/512", config="R5/R2/R3/R4",
         description="复刻几何的直线+弯曲损耗与原版 Python 3.8 字节码实跑逐路完全一致（max|Δ|=0）",
         data_files=["OpticalWaveguideRouter2D/scratch/legacy_loss/legacy256_R5.json",
                     "OpticalWaveguideRouter2D/scratch/legacy_loss/legacy512_R2.json",
                     "OpticalWaveguideRouter2D/scratch/legacy_loss/legacy512_R3.json",
                     "OpticalWaveguideRouter2D/scratch/legacy_loss/legacy512_R4.json",
                     "OpticalWaveguideRouter2D/scratch/legacy_loss/legacy512_R5.json"],
         metrics="per-route 非交叉 loss", figures="f39", tables="--", status="有效",
         notes="legacy 交叉为全 0 占位表，只用于非交叉项对照。"),
    # ---- Step 12 ----
    dict(id="S12-01", group="Step 12", name="A/B/C/D 主对照",
         scale="256/512", config="A 原版 / B 统一 R6 / C 候选轨道 / D 自适应半径",
         description="候选轨道优化与自适应半径的主结果（B 为参数对照）",
         data_files=["OpticalWaveguideRouter3D/outputs/opt2d/{256,512}/comparison.csv",
                     "OpticalWaveguideRouter3D/outputs/opt2d/{256,512}/comparison.json"],
         metrics="mean/p95/max_loss_db、unplaced、unique_crossing_events、spacing、runtime",
         figures="f51;f52;f54", tables="t51", status="有效",
         notes="512 的 B 有 2 条未布通（incomplete），不可与完整方案同口径比较。"),
    dict(id="S12-02", group="Step 12", name="消融：候选数 K=1/4/8/16",
         scale="256/512", config="candidate_limit",
         description="候选轨道数量的消融",
         data_files=["OpticalWaveguideRouter3D/outputs/opt2d/{256,512}/sensitivity.json",
                     "OpticalWaveguideRouter3D/outputs/opt2d/{256,512}/sensitivity/cand_k*/summary.json"],
         metrics="mean_loss_db、unplaced、runtime", figures="f53;f54", tables="t52",
         status="有效", notes="默认 K=8。"),
    dict(id="S12-03", group="Step 12", name="消融：布线顺序 span/congestion",
         scale="256/512", config="order_strategy",
         description="顺序策略消融（含未布通结果）",
         data_files=["OpticalWaveguideRouter3D/outputs/opt2d/{256,512}/sensitivity.json"],
         metrics="mean_loss_db、unplaced", figures="f53;f54", tables="t52",
         status="有效", notes="256 span 未布通 76、512 span 未布通 144；保留展示不参与排名。"),
    dict(id="S12-04", group="Step 12", name="消融：拆线重布开/关",
         scale="256/512", config="refine_rounds=3",
         description="有界拆线重布消融",
         data_files=["OpticalWaveguideRouter3D/outputs/opt2d/{256,512}/sensitivity.json"],
         metrics="mean_loss_db、runtime", figures="f53;f54", tables="t52",
         status="有效", notes="与默认配置结果一致（在 K=8 下未进一步改进）。"),
    dict(id="S12-05", group="Step 12", name="消融：位置正则 0/0.001/0.01/0.05",
         scale="256/512", config="position_penalty",
         description="位置正则强度消融",
         data_files=["OpticalWaveguideRouter3D/outputs/opt2d/{256,512}/sensitivity.json"],
         metrics="mean_loss_db、unplaced", figures="f53;f54", tables="t52",
         status="有效", notes="256 默认 0.001、512 默认 0.01；0 在两类规模上均产生未布通。"),
    dict(id="S12-06", group="Step 12", name="消融：半径策略 fixed_R6/adaptive",
         scale="256/512", config="radii",
         description="半径策略消融（与 B/D 呼应）",
         data_files=["OpticalWaveguideRouter3D/outputs/opt2d/{256,512}/sensitivity.json"],
         metrics="mean_loss_db、radius_distribution", figures="f53;f54", tables="t52",
         status="有效", notes="512 fixed_R6 有 2 条未布通。"),
    # ---- Step 13 ----
    dict(id="S13-01", group="Step 13", name="六方案旧版（固定端点）",
         scale="256/512", config="A/R5U/D0/D56/F5/F56",
         description="固定端点六方案对照（旧版产物；256 F56 含历史非法几何 #7/#31 重合）",
         data_files=["OpticalWaveguideRouter3D/outputs/opt2d_step13/{256,512}/comparison.csv",
                     "OpticalWaveguideRouter3D/outputs/opt2d_step13/{256,512}/worst_route_tracking.csv"],
         metrics="mean/p95/max_loss_db、交叉、转角", figures="f63;f64", tables="--",
         status="历史", notes="256 F56 #7/#31 重合 152.007 mm 为历史非法几何；最终排名使用补修版。"),
    dict(id="S13-02", group="Step 13", name="六方案补修版（重布 #7/#31）",
         scale="256/512", config="A/R5U/D0/D56/F5/F56（fix）",
         description="补修后有效结果：256 F56 48 条路线重布；512 逐项不变",
         data_files=["OpticalWaveguideRouter3D/outputs/opt2d_step13_fix/{256,512}/comparison.csv",
                     "OpticalWaveguideRouter3D/outputs/opt2d_step13_fix/256/per_route_delta.csv"],
         metrics="mean/p95/max_loss_db、接触两口径", figures="f61;f62;f64", tables="t61;t62",
         status="有效", notes="最终推荐与排名基于本版。"),
    dict(id="S13-03", group="Step 13", name="受约束复算 base/spacing/small/both",
         scale="256/512", config="间距/小角惩罚（固定几何）",
         description="只改评分不改几何的约束复算；spacing/small/both 降低违规、平均损耗略升",
         data_files=["OpticalWaveguideRouter3D/outputs/opt2d_step13_constrained/{256,512}/constrained_comparison.csv"],
         metrics="mean/max_loss_db、<5/<10/<20°、间距、接触",
         figures="f65", tables="t63", status="有效",
         notes="与 Step 14 的冻结半径实验条件不同（本组同时换了几何族，不能作纯约束对照）。"),
    dict(id="S13-04", group="Step 13", name="交叉表压力情景 ×1/×2/×5/×10",
         scale="256/512", config="<20° 放大（fix 版）",
         description="固定几何复算：F56 最大损耗在 ×10 时 6.00（256）/ 8.43（512）dB",
         data_files=["OpticalWaveguideRouter3D/outputs/opt2d_step13_fix/{256,512}/sensitivity.csv"],
         metrics="mean/p95/max/sum_loss_db", figures="f66", tables="t64",
         status="有效", notes="×5/×10 是压力情景，不代表已验证的真实误差范围。"),
    dict(id="S13-05", group="Step 13", name="间距惩罚强度扫描 0.02/0.05",
         scale="256/512", config="F5/F56 × spacing_penalty",
         description="惩罚强度与间距违规/损耗的权衡",
         data_files=["OpticalWaveguideRouter3D/outputs/opt2d_step13_fix/{256,512}/penalty_ablation_F5.csv",
                     "OpticalWaveguideRouter3D/outputs/opt2d_step13_fix/{256,512}/penalty_ablation_F56.csv"],
         metrics="mean/max_loss_db、spacing、touch", figures="f67", tables="--", status="有效",
         notes="0 dB 行取自 comparison.csv。"),
    dict(id="S13-06", group="Step 13", name="最差路线跟踪",
         scale="256/512", config="A 最差路线（#44 / #287）",
         description="最差路线在六方案中的损耗分解、交叉数与总转角",
         data_files=["OpticalWaveguideRouter3D/outputs/opt2d_step13/{256,512}/worst_route_tracking.csv"],
         metrics="total/straight/bend/crossing_loss、crossing_count、bend_total_deg",
         figures="f63", tables="--", status="有效", notes="最差路线分别为 256 #44、512 #287。"),
    dict(id="S13-07", group="Step 13", name="半径对照 D56 vs F56（核对）",
         scale="256/512", config="逐路半径一致性",
         description="D56 与 F56 的逐路半径完全相同（全部 same=True）",
         data_files=["OpticalWaveguideRouter3D/outputs/opt2d_step13_fix/{256,512}/radius_compare.csv"],
         metrics="same_radius", figures="--", tables="--", status="核对",
         notes="一致性核对项（非实验配置）；结果全部一致，记录于质量审查报告。"),
    # ---- Step 14 ----
    dict(id="S14-01", group="Step 14", name="冻结半径六配置主对照",
         scale="256/512", config="base/spacing/small/touch/both/opt_base",
         description="Step 14 冻结半径公平对照；opt_base 为保护性局部优化",
         data_files=["OpticalWaveguideRouter3D/outputs/opt2d_step14/{256,512}/comparison.csv"],
         metrics="mean/p95/max、小角计数、间距、接触两口径", figures="f71;f73", tables="t71",
         status="有效", notes="touch≡base（物理接触为 0）。"),
    dict(id="S14-02", group="Step 14", name="严格验收",
         scale="256/512", config="AcceptanceRule（mean_slack 0.05 dB）",
         description="spacing/small/both 未通过（保护对象劣化）；opt_base 通过",
         data_files=["OpticalWaveguideRouter3D/outputs/opt2d_step14/{256,512}/acceptance.csv"],
         metrics="ok、reasons、mean/max_delta", figures="f71;f72", tables="t71",
         status="有效", notes="未通过方案仍展示，不标为最终推荐。"),
    dict(id="S14-03", group="Step 14", name="保护余量曲线",
         scale="256/512", config="余量 0–0.02 dB",
         description="固定保护集合的逐路劣化与不同余量下的通过情况",
         data_files=["OpticalWaveguideRouter3D/outputs/opt2d_step14/{256,512}/protection_margins.csv"],
         metrics="max_violation_db、violating/improved_routes", figures="f74", tables="t72",
         status="有效", notes="余量放宽属诊断口径，任务口径为 0 dB。"),
    dict(id="S14-04", group="Step 14", name="固定保护对象逐路差值",
         scale="256/512", config="11 条固定 ID（Step 14 保存）",
         description="同一保护集合在六配置下的逐路损耗差值矩阵",
         data_files=["OpticalWaveguideRouter3D/outputs/opt2d_step14/{256,512}/protection_set.json",
                     "OpticalWaveguideRouter3D/outputs/opt2d_step14/{256,512}/{scheme}/protection_routes.csv"],
         metrics="delta_vs_base_db", figures="f74", tables="t72", status="有效",
         notes="禁止逐方案重选 top-10；所有配置使用同一集合。"),
    dict(id="S14-05", group="Step 14", name="opt_base 接受过程与拒绝原因",
         scale="256/512", config="candidates_per_route=4、scenario_top=16",
         description="256 接受 0/68、512 接受 6/74；回滚指纹不一致为 0",
         data_files=["OpticalWaveguideRouter3D/outputs/opt2d_step14/{256,512}/optimize_attempts_base.csv",
                     "OpticalWaveguideRouter3D/outputs/opt2d_step14/{256,512}/optimize_record.json"],
         metrics="scenario_gain_db、accepted、rejected 原因", figures="f75", tables="t73",
         status="有效", notes="512 的 comparison.runtime_s=0.0 为脚本字段陷阱，真实耗时 762.24 s 在 optimize_record。"),
    dict(id="S14-06", group="Step 14", name="诊断探针（放宽余量/加严排序）",
         scale="256/512", config="rank_small*/strict_slack*",
         description="诊断口径：加严排序 0 接受；放宽余量在 512 接受 5 次",
         data_files=["OpticalWaveguideRouter3D/outputs/opt2d_step14/{256,512}/probe/probe_summary.csv"],
         metrics="accepted、scenario_gain_db", figures="f76", tables="t73", status="诊断",
         notes="明确是诊断，不是任务验收口径。"),
    dict(id="S14-07", group="Step 14", name="压力情景 ×1/×2/×5/×10",
         scale="256/512", config="<20° 放大（六配置）",
         description="512 opt_base ×10 最大损耗 8.4333→8.4996 dB（略恶化）；×1–×5 下降",
         data_files=["OpticalWaveguideRouter3D/outputs/opt2d_step14/{256,512}/sensitivity.csv"],
         metrics="mean/p95/max_loss_db", figures="f77", tables="t74", status="有效",
         notes="如实呈现 ×10 的轻微恶化，不写成全面稳健。"),
    dict(id="S14-08", group="Step 14", name="半径冻结核对（核对）",
         scale="256/512", config="逐路半径 = F56",
         description="全部路线冻结半径与 F56 完全一致（256: 256/256；512: 512/512）",
         data_files=["OpticalWaveguideRouter3D/outputs/opt2d_step14/{256,512}/radius_freeze_check.csv"],
         metrics="same", figures="--", tables="--", status="核对",
         notes="一致性核对项；结果全部一致，记录于质量审查报告。"),
    dict(id="S14-09", group="Step 14", name="D56/F56 参照评价",
         scale="256/512", config="同时评价 D56 与 F56",
         description="Step 14 口径下 D56/F56 的标称与情景指标（供对照）",
         data_files=["OpticalWaveguideRouter3D/outputs/opt2d_step14/{256,512}/references.csv"],
         metrics="mean/p95/max、scenario5", figures="f72", tables="t72", status="参照",
         notes="用于说明 base 与 F56 的关系。"),
    # ---- 三维 ----
    dict(id="G3D-01", group="三维", name="9-A 三维几何基础",
         scale="512（6 条样本）", config="lift 到测试层",
         description="几何容器与 lift 的验证（无路由实验）",
         data_files=["OpticalWaveguideRouter3D/outputs/step_9_a_tests.json"],
         metrics="测试 545 通过", figures="--", tables="--", status="验证",
         notes="基础验证步：没有实验参数组合，不在图覆盖范围。"),
    dict(id="G3D-02", group="三维", name="9-B 余弦过渡曲率验证",
         scale="解析验证", config="R_min 公式",
         description="余弦过渡的曲率/最小半径解析-数值一致（误差 6.4e-12）",
         data_files=["OpticalWaveguideRouter3D/outputs/step_9_b_curvature_join_validation.json"],
         metrics="curvature error", figures="--", tables="--", status="验证",
         notes="纯数学验证步。"),
    dict(id="G3D-03", group="三维", name="9-C clearance 与碰撞基础",
         scale="6 对样本", config="clearance 0.01 mm",
         description="距离分类与自适应最小距离验证",
         data_files=["OpticalWaveguideRouter3D/outputs/step_9_c_clearance_validation.json"],
         metrics="150 primitive pairs", figures="--", tables="--", status="验证",
         notes="基础验证步。"),
    dict(id="G3D-04", group="三维", name="9-D 单路线抬层探针",
         scale="512（3 组路线对）", config="两层、clearance 0.1 mm",
         description="3 组真实 pair 抬层、逐组校验 511 邻居、零新建碰撞（总 68.6 s）",
         data_files=["OpticalWaveguideRouter3D/outputs/step_9_d_probe_summary.json",
                     "OpticalWaveguideRouter3D/outputs/step_9_d_local_validation.json"],
         metrics="old/new collision count、removed 列表", figures="f80", tables="--",
         status="有效", notes="单路线可行性探针（不是多路线分配）。"),
    dict(id="G3D-05", group="三维", name="9-E 小规模顺序层分配",
         scale="512", config="两层、30 次 attempt",
         description="12 次成功抬层、近距 pair 49518→47508（−4.06%）",
         data_files=["OpticalWaveguideRouter3D/outputs/step_9_e_sequential_elevation_summary.json",
                     "OpticalWaveguideRouter3D/outputs/step_9_e_sequential_elevation_steps.csv"],
         metrics="collision pairs、elevations、extra length、runtime", figures="f81", tables="t81",
         status="有效", notes="几何指标；与二维 cross 事件口径不同。"),
    dict(id="G3D-06", group="三维", name="9-F 两层对照",
         scale="512", config="两层、50 次 attempt",
         description="16 次成功抬层、49518→46624（−5.84%）",
         data_files=["OpticalWaveguideRouter3D/outputs/step_9_f_two_layer_control_summary.json"],
         metrics="collision pairs、elevations、extra length、runtime",
         figures="f81;f82", tables="t81", status="有效", notes="与三层同条件对照。"),
    dict(id="G3D-07", group="三维", name="9-F 三层顺序分配",
         scale="512", config="三层、50 次 attempt",
         description="22 次成功抬层、49518→45400（−8.32%）；第三层额外收益 1224 对",
         data_files=["OpticalWaveguideRouter3D/outputs/step_9_f_three_layer_summary.json",
                     "OpticalWaveguideRouter3D/outputs/step_9_f_comparison.json",
                     "OpticalWaveguideRouter3D/outputs/step_9_f_layer_usage.json"],
         metrics="collision pairs、layer usage、extra length", figures="f81;f82",
         tables="t81", status="有效", notes="层 2 独有成功数为 0（第三层收益来自更优替代）。"),
    dict(id="G3D-08", group="三维", name="10 固定 1024 三层布线",
         scale="1024（合成实例 300×200）", config="三层、上限 1024 次 attempt",
         description="175 次抬层、350 个过渡、近距 pair 204291→138113（−32.39%）、额外 87.4 mm、1172.7 s",
         data_files=["OpticalWaveguideRouter3D/outputs/step_10_fixed_1024_summary.json",
                     "OpticalWaveguideRouter3D/outputs/step_10_fixed_1024_final_route_state.json"],
         metrics="collision pairs、layer counts、runtime 分解", figures="f83;f84;f85;f86",
         tables="t81", status="有效",
         notes="合成压力实例；−32.39% 是自定义近距 pair 计数，不是制造违规或光学风险。"),
    dict(id="G3D-09", group="三维", name="11 三维可视化（重绘）",
         scale="1024", config="13 张原图（发布版重绘 4 张）",
         description="XY 投影、XZ 侧视、三维总览、抬层示例（由终态几何重绘）",
         data_files=["OpticalWaveguideRouter3D/outputs/step_10_fixed_1024_final_route_state.json",
                     "OpticalWaveguideRouter3D/outputs/step_11_visualization_summary.json"],
         metrics="planar_section_counts、examples", figures="f84;f85;f86", tables="--",
         status="有效", notes="发布版图由只读几何重绘，风格统一。"),
    dict(id="G3D-10", group="三维", name="8.5 legacy 512 二维基线",
         scale="512", config="精确求交（物理口径）",
         description="供三维对照的二维基线（55935 事件、49502 对）",
         data_files=["OpticalWaveguideRouter3D/outputs/step_8_5_legacy_512_physical_summary.json"],
         metrics="cross_events、cross_pairs", figures="f38", tables="t33（对照说明）",
         status="参照", notes="与三维 collision pair 定义不同，仅作背景，不作数值差比较。"),
]

# ---------------------------------------------------------------------------
# 图覆盖表
# ---------------------------------------------------------------------------

FIGURES = [
    dict(id="f31", title="90° 弯曲损耗：论文表 3-1 与复刻模型对照", section="3.1",
         output="f31_bend_model_thesis_vs_repro", experiments="R01",
         sources="论文表 3-1（引用记录）；OpticalWaveguideRouter2D/loss_model.py"),
    dict(id="f32", title="论文值与复现值对照与有符号误差", section="3.2",
         output="f32_reproduction_accuracy", experiments="R02;R03;R04",
         sources="results/fiberBoard{256,512}_loss_summary.json 等"),
    dict(id="f33", title="512 通道半径扫描（R2–R5）与弯曲占比", section="3.3",
         output="f33_radius_sweep_512", experiments="R04;R05;R06;R03",
         sources="results/fiberBoard512_loss_R{2,3,4}_summary.json、fiberBoard512_loss_summary.json"),
    dict(id="f34", title="复现损耗分量分解（直线/弯曲/交叉）", section="3.3",
         output="f34_loss_contribution_repro", experiments="R02;R03;R04;R05;R06",
         sources="results/*_loss_summary.json"),
    dict(id="f35", title="逐路损耗分布与累计分布", section="3.4",
         output="f35_loss_distribution_repro", experiments="R02;R03",
         sources="results/fiberBoard{256,512}_loss.xlsx"),
    dict(id="f36", title="损耗—长度 / 损耗—交叉数散点", section="3.4",
         output="f36_loss_structure_scatter", experiments="R02;R03",
         sources="results/fiberBoard{256,512}_loss.xlsx"),
    dict(id="f37", title="交叉角度分布与小角放大", section="3.5",
         output="f37_crossing_angle_distribution", experiments="R02;R03",
         sources="results/fiberBoard{256,512}_loss.xlsx（crossing_angles_deg）"),
    dict(id="f38", title="legacy 512 精确几何审计（物理口径）", section="3.5",
         output="f38_legacy_geometric_audit", experiments="R08;G3D-10",
         sources="outputs/step_8_5_legacy_512_*.json"),
    dict(id="f39", title="复刻与原版字节码逐路对照", section="3.6",
         output="f39_legacy_bytecode_check", experiments="R09",
         sources="scratch/legacy_loss/legacy*.json、results/fiberBoard*_loss.xlsx"),
    dict(id="f310", title="交叉模型三口径敏感性", section="3.6",
         output="f310_crossing_model_sensitivity", experiments="R07",
         sources="data/crossing_loss_from_thesis_fig3_12.csv、results/fiberBoard512_loss.xlsx"),
    dict(id="f51", title="Step 12 主结果（A–D，mean/P95/max）", section="5.1",
         output="f51_step12_main", experiments="S12-01",
         sources="outputs/opt2d/{256,512}/comparison.csv"),
    dict(id="f52", title="Step 12 损耗分量分解", section="5.1",
         output="f52_step12_loss_breakdown", experiments="S12-01",
         sources="outputs/opt2d/{256,512}/comparison.csv"),
    dict(id="f53", title="Step 12 消融（候选数/顺序/拆线/正则/半径）", section="5.2",
         output="f53_step12_ablation", experiments="S12-02;S12-03;S12-04;S12-05;S12-06",
         sources="outputs/opt2d/{256,512}/sensitivity.json"),
    dict(id="f54", title="运行时间—平均损耗（效率视角）", section="5.3",
         output="f54_step12_efficiency", experiments="S12-01;S12-02;S12-03;S12-04;S12-05;S12-06",
         sources="outputs/opt2d/{256,512}/comparison.csv、sensitivity.json"),
    dict(id="f61", title="Step 13 补修版主结果（六方案）", section="6.1",
         output="f61_step13_main", experiments="S13-02",
         sources="outputs/opt2d_step13_fix/{256,512}/comparison.csv"),
    dict(id="f62", title="Step 13 分量分解（交叉升高的代价）", section="6.1",
         output="f62_step13_breakdown", experiments="S13-02",
         sources="outputs/opt2d_step13_fix/{256,512}/comparison.csv"),
    dict(id="f63", title="最差路线跟踪（#44 / #287）", section="6.2",
         output="f63_step13_worst_route", experiments="S13-01;S13-06",
         sources="outputs/opt2d_step13/{256,512}/worst_route_tracking.csv"),
    dict(id="f64", title="补修前后差异（256 F56 的 48 条）", section="6.2",
         output="f64_step13_fix_delta", experiments="S13-01;S13-02",
         sources="outputs/opt2d_step13_fix/256/per_route_delta.csv 等"),
    dict(id="f65", title="受约束复算的权衡（间距/小角 vs 损耗）", section="6.3",
         output="f65_step13_constrained", experiments="S13-03",
         sources="outputs/opt2d_step13_constrained/{256,512}/constrained_comparison.csv"),
    dict(id="f66", title="交叉表压力情景（×1/×2/×5/×10）", section="6.4",
         output="f66_step13_sensitivity", experiments="S13-04",
         sources="outputs/opt2d_step13_fix/{256,512}/sensitivity.csv"),
    dict(id="f67", title="间距惩罚强度扫描（0/0.02/0.05）", section="6.3",
         output="f67_step13_penalty_ablation", experiments="S13-05",
         sources="outputs/opt2d_step13_fix/{256,512}/penalty_ablation_F*.csv"),
    dict(id="f71", title="Step 14 冻结半径六配置主对照与验收", section="7.1",
         output="f71_step14_main", experiments="S14-01;S14-02",
         sources="outputs/opt2d_step14/{256,512}/comparison.csv、acceptance.csv"),
    dict(id="f72", title="×5 压力情景与 opt_base 改善", section="7.2",
         output="f72_step14_scenario5", experiments="S14-01;S14-02;S14-09",
         sources="outputs/opt2d_step14/{256,512}/comparison.csv、references.csv"),
    dict(id="f73", title="小角度交叉计数（<5°/<10°/<20°）", section="7.2",
         output="f73_step14_small_angle", experiments="S14-01",
         sources="outputs/opt2d_step14/{256,512}/comparison.csv"),
    dict(id="f74", title="固定保护对象逐路差值热力图", section="7.3",
         output="f74_step14_protection_delta", experiments="S14-03;S14-04",
         sources="outputs/opt2d_step14/{256,512}/protection_set.json、{scheme}/protection_routes.csv"),
    dict(id="f75", title="opt_base 接受过程与拒绝原因", section="7.4",
         output="f75_step14_optimize_process", experiments="S14-05",
         sources="outputs/opt2d_step14/{256,512}/optimize_attempts_base.csv、optimize_record.json"),
    dict(id="f76", title="诊断探针变体对照", section="7.4",
         output="f76_step14_probe_variants", experiments="S14-06",
         sources="outputs/opt2d_step14/{256,512}/probe/probe_summary.csv"),
    dict(id="f77", title="Step 14 压力情景（×1–×10，含 ×10 恶化）", section="7.5",
         output="f77_step14_sensitivity", experiments="S14-07",
         sources="outputs/opt2d_step14/{256,512}/sensitivity.csv"),
    dict(id="f80", title="9-D 单路线抬层探针", section="8.1",
         output="f80_3d_probe_9d", experiments="G3D-04",
         sources="outputs/step_9_d_probe_summary.json、step_9_d_local_validation.json"),
    dict(id="f81", title="三维层分配与近距 pair 净减少", section="8.2",
         output="f81_3d_layer_assignment", experiments="G3D-05;G3D-06;G3D-07",
         sources="outputs/step_9_e_*.json、step_9_f_*.json"),
    dict(id="f82", title="两层 vs 三层对照", section="8.2",
         output="f82_3d_two_vs_three", experiments="G3D-06;G3D-07",
         sources="outputs/step_9_f_two_layer_control_summary.json、step_9_f_three_layer_summary.json"),
    dict(id="f83", title="固定 1024：近距 pair/层使用/运行分解", section="8.3",
         output="f83_3d_fixed_1024", experiments="G3D-08",
         sources="outputs/step_10_fixed_1024_summary.json"),
    dict(id="f84", title="1024 终态 XY 投影（按层着色）", section="8.3",
         output="f84_3d_xy_projection", experiments="G3D-08;G3D-09",
         sources="outputs/step_10_fixed_1024_final_route_state.json（只读重绘）"),
    dict(id="f85", title="1024 终态 XZ 侧视与抬层示例", section="8.3",
         output="f85_3d_xz_side", experiments="G3D-08;G3D-09",
         sources="outputs/step_10_fixed_1024_final_route_state.json（只读重绘）"),
    dict(id="f86", title="1024 三维总览（z 放大 ×20）", section="8.3",
         output="f86_3d_overview", experiments="G3D-08;G3D-09",
         sources="outputs/step_10_fixed_1024_final_route_state.json（只读重绘）"),
]

# ---------------------------------------------------------------------------
# 表覆盖表
# ---------------------------------------------------------------------------

TABLES = [
    dict(id="t31", title="弯曲模型论文/复刻对照", experiments="R01",
         sources="论文表 3-1；loss_model.py"),
    dict(id="t32", title="论文值与复现值对照", experiments="R02;R03;R04",
         sources="results/*_summary.json"),
    dict(id="t33", title="512 半径扫描明细", experiments="R03;R04;R05;R06;G3D-10",
         sources="results/fiberBoard512_loss_R*_summary.json"),
    dict(id="t34", title="交叉模型敏感性（三口径）", experiments="R07",
         sources="data/crossing_loss_from_thesis_fig3_12.csv；逐路明细复算"),
    dict(id="t51", title="Step 12 主表", experiments="S12-01", sources="outputs/opt2d/*/comparison.csv"),
    dict(id="t52", title="Step 12 消融表", experiments="S12-02;S12-03;S12-04;S12-05;S12-06",
         sources="outputs/opt2d/*/sensitivity.json"),
    dict(id="t61", title="Step 13 补修版主表", experiments="S13-02",
         sources="outputs/opt2d_step13_fix/*/comparison.csv"),
    dict(id="t62", title="Step 13 代价表", experiments="S13-02", sources="同上"),
    dict(id="t63", title="受约束复算表", experiments="S13-03",
         sources="outputs/opt2d_step13_constrained/*/constrained_comparison.csv"),
    dict(id="t64", title="Step 13 压力情景表", experiments="S13-04",
         sources="outputs/opt2d_step13_fix/*/sensitivity.csv"),
    dict(id="t71", title="Step 14 主表与验收", experiments="S14-01;S14-02",
         sources="outputs/opt2d_step14/*/comparison.csv、acceptance.csv"),
    dict(id="t72", title="压力情景与保护余量表", experiments="S14-01;S14-03;S14-09",
         sources="outputs/opt2d_step14/*/comparison.csv、protection_margins.csv"),
    dict(id="t73", title="接受统计与诊断表", experiments="S14-05;S14-06",
         sources="outputs/opt2d_step14/*/optimize_record.json、probe/probe_summary.csv"),
    dict(id="t74", title="Step 14 压力情景表", experiments="S14-07",
         sources="outputs/opt2d_step14/*/sensitivity.csv"),
    dict(id="t81", title="三维实验汇总", experiments="G3D-05;G3D-06;G3D-07;G3D-08",
         sources="outputs/step_9_*/step_9_*_summary.json、step_10_fixed_1024_summary.json"),
]


def _check_outputs() -> list[str]:
    problems = []
    for figure in FIGURES:
        for ext in ("pdf", "svg", "png"):
            path = Path(S.PROJECT_ROOT) / OUT_FIG / f"{figure['output']}.{ext}"
            if not path.exists():
                problems.append(f"缺少图输出：{path}")
    for table in TABLES:
        filename = TABLE_FILENAMES[table["id"]]
        for suffix in (".tex", "_data.csv"):
            path = Path(S.PROJECT_ROOT) / OUT_TAB / f"{filename}{suffix}"
            if not path.exists():
                problems.append(f"缺少表输出：{path}")
    return problems


# 表文件名与 id 不总是一致（含描述后缀），此处用真实文件名映射
TABLE_FILENAMES = {
    "t31": "t31_bend_model_thesis_vs_repro",
    "t32": "t32_reproduction_compare",
    "t33": "t33_radius_sweep_512",
    "t34": "t34_crossing_model_sensitivity",
    "t51": "t51_step12_main",
    "t52": "t52_step12_ablation",
    "t61": "t61_step13_main",
    "t62": "t62_step13_cost",
    "t63": "t63_step13_constrained",
    "t64": "t64_step13_sensitivity",
    "t71": "t71_step14_main",
    "t72": "t72_step14_scenario",
    "t73": "t73_step14_optimize",
    "t74": "t74_step14_sensitivity",
    "t81": "t81_3d_experiments",
}


def generate() -> None:
    import csv

    MANIFEST.mkdir(parents=True, exist_ok=True)

    with (MANIFEST / "experiment_inventory.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["experiment_id", "group", "name", "scale", "config",
                         "description", "data_files", "key_metrics", "figures",
                         "tables", "status", "notes"])
        for item in EXPERIMENTS:
            writer.writerow([item["id"], item["group"], item["name"], item["scale"],
                             item["config"], item["description"],
                             ";".join(item["data_files"]), item["metrics"],
                             item["figures"], item["tables"], item["status"], item["notes"]])

    with (MANIFEST / "figure_coverage.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["figure_id", "title", "section", "output_stem", "outputs",
                         "experiments", "sources"])
        for figure in FIGURES:
            outputs = ";".join(f"{OUT_FIG}/{figure['output']}.{ext}" for ext in ("pdf", "svg", "png"))
            writer.writerow([figure["id"], figure["title"], figure["section"],
                             figure["output"], outputs, figure["experiments"], figure["sources"]])

    with (MANIFEST / "table_coverage.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["table_id", "title", "tex", "data_csv", "experiments", "sources"])
        for table in TABLES:
            filename = TABLE_FILENAMES[table["id"]]
            writer.writerow([table["id"], table["title"],
                             f"{OUT_TAB}/{filename}.tex",
                             f"{OUT_TAB}/{filename}_data.csv",
                             table["experiments"], table["sources"]])

    # 覆盖闭合性检查：每个实验至少被一张图或一张表覆盖
    # （核对与基础验证步按设计不绘图：核对为一致性检查，验证步没有参数组合）
    problems = []
    uncovered_verification = []
    covered_by_figure = set()
    for figure in FIGURES:
        covered_by_figure.update(figure["experiments"].split(";"))
    covered_by_table = set()
    for table in TABLES:
        covered_by_table.update(table["experiments"].split(";"))
    for item in EXPERIMENTS:
        if item["status"] in ("核对", "验证"):
            if item["id"] not in covered_by_figure and item["id"] not in covered_by_table:
                uncovered_verification.append(item["id"])
            continue
        if item["id"] not in covered_by_figure and item["id"] not in covered_by_table:
            problems.append(f"实验 {item['id']}（{item['name']}）无图/表覆盖")
        if item["status"] in ("有效", "历史", "诊断", "参照") and item["id"] not in covered_by_figure:
            problems.append(f"实验 {item['id']}（{item['name']}）没有图形覆盖（仅有表）")
    problems.extend(_check_outputs())
    if uncovered_verification:
        print(f"  [清单] 验证/核对步（按设计不绘图）：{', '.join(uncovered_verification)}")
    if problems:
        print("  [清单] 覆盖问题：")
        for problem in problems:
            print("    -", problem)
    else:
        print("  [清单] 覆盖闭合：全部实验均被图覆盖")
    print(f"  [清单] 实验 {len(EXPERIMENTS)} 项、图 {len(FIGURES)} 张、表 {len(TABLES)} 张")
