"""报告内容模块：文本、图题、表题与数字注入。

数字来源：publication 的表格 _data.csv 与 opt2d 系列产物（经 pubdata 读取）。
正文中的关键数字以 {占位} 从 DATA 注入，生成时若实验文件变化会同步更新。
"""

from __future__ import annotations

from pathlib import Path

import pubdata as D

PROJECT_ROOT = D.PROJECT_ROOT
FIGURE_DIR = PROJECT_ROOT / "publication" / "figures"
TABLE_DIR = PROJECT_ROOT / "publication" / "tables"
MANIFEST_DIR = PROJECT_ROOT / "publication" / "manifest"

# ---------------------------------------------------------------------------
# 关键数字（全部从实验产物读取，不硬编码）
# ---------------------------------------------------------------------------

_r256 = D.repro_summary("256_R5")
_r512 = D.repro_summary("512_R5")
_r4 = D.repro_summary("512_R4")
_s13_256 = D.step13_comparison(256, fixed=True).set_index("scheme")
_s13_512 = D.step13_comparison(512, fixed=True).set_index("scheme")
_s14_256 = D.step14_comparison(256).set_index("scheme")
_s14_512 = D.step14_comparison(512).set_index("scheme")
_acc512 = D.step14_acceptance(512).set_index("scheme")
_rec_256 = D.step14_optimize_record(256)["opt_base"]
_rec_512 = D.step14_optimize_record(512)["opt_base"]
_margin512 = D.step14_margins(512).set_index("scheme")
_scen_512 = D.step14_sensitivity(512)
_sens13_256 = D.step13_fix_sensitivity(256)
_sens13_512 = D.step13_fix_sensitivity(512)
_9e = D.step9e_summary()
_9f2 = D.step9f_two_layer_summary()
_9f3 = D.step9f_three_layer_summary()
_10 = D.step10_summary()
_cross_sens = D.crossing_sensitivity()


def _f(value: float, nd: int = 4) -> str:
    return f"{value:.{nd}f}"


def _gain(rel: float) -> str:
    return f"{abs(rel) * 100:.1f}%"


DATA = {
    # 复现
    "r256_mean": _f(_r256["mean_loss_db"]), "r256_max": _f(_r256["max_loss_db"]),
    "r512_mean": _f(_r512["mean_loss_db"]), "r512_max": _f(_r512["max_loss_db"]),
    "r4_mean": _f(_r4["mean_loss_db"]), "r4_max": _f(_r4["max_loss_db"]),
    "r256_p95": _f(D.repro_percentile("256_R5", 95)),
    "r512_p95": _f(D.repro_percentile("512_R5", 95)),
    "r4_p95": _f(D.repro_percentile("512_R4", 95)),
    "bend_r2": _f(D.bend_model_90_db(2.0)), "bend_r5": _f(D.bend_model_90_db(5.0)),
    "bend_r6": _f(D.bend_model_90_db(6.0)),
    # 复现扫描
    "rs_R2_mean": _f(D.repro_summary("512_R2")["mean_loss_db"]),
    "rs_R3_mean": _f(D.repro_summary("512_R3")["mean_loss_db"]),
    "rs_R4_mean": _f(_r4["mean_loss_db"]),
    "rs_R5_mean": _f(_r512["mean_loss_db"]),
    "bend_share_R2": f"{D.repro_summary('512_R2')['loss_contribution']['bend'] * 100:.1f}",
    "bend_share_R5": f"{_r512['loss_contribution']['bend'] * 100:.1f}",
    # 交叉敏感性
    "cs_A_mean": _f(_cross_sens["A"]["mean"]), "cs_B_mean": _f(_cross_sens["B"]["mean"]),
    "cs_C_mean": _f(_cross_sens["C"]["mean"]), "cs_A_max": _f(_cross_sens["A"]["max"]),
    "cs_B_max": _f(_cross_sens["B"]["max"]), "cs_C_max": _f(_cross_sens["C"]["max"]),
    # Step 12
    "s12_A_256_mean": _f(D.step12_comparison(256).set_index("label").loc["A-R5-legacy", "mean_loss_db"]),
    "s12_B_256_mean": _f(D.step12_comparison(256).set_index("label").loc["B-R6", "mean_loss_db"]),
    "s12_A_512_mean": _f(D.step12_comparison(512).set_index("label").loc["A-R5-legacy", "mean_loss_db"]),
    "s12_B_512_mean": _f(D.step12_comparison(512).set_index("label").loc["B-R6", "mean_loss_db"]),
    "s12_B_512_unplaced": int(D.step12_comparison(512).set_index("label").loc["B-R6", "unplaced_count"]),
    # Step 13（补修版）
    "s13_256_F56_mean": _f(_s13_256.loc["F56", "mean_loss_db"]),
    "s13_256_F56_p95": _f(_s13_256.loc["F56", "p95_loss_db"]),
    "s13_256_F56_max": _f(_s13_256.loc["F56", "max_loss_db"]),
    "s13_256_D56_mean": _f(_s13_256.loc["D56", "mean_loss_db"]),
    "s13_256_R5U_mean": _f(_s13_256.loc["R5U", "mean_loss_db"]),
    "s13_256_A_max": _f(_s13_256.loc["A", "max_loss_db"]),
    "s13_512_F56_mean": _f(_s13_512.loc["F56", "mean_loss_db"]),
    "s13_512_F56_max": _f(_s13_512.loc["F56", "max_loss_db"]),
    "s13_512_D56_mean": _f(_s13_512.loc["D56", "mean_loss_db"]),
    "s13_512_A_mean": _f(_s13_512.loc["A", "mean_loss_db"]),
    "s13_256_improve": _gain(1 - _s13_256.loc["F56", "mean_loss_db"] / _s13_256.loc["A", "mean_loss_db"]),
    "s13_512_improve": _gain(1 - _s13_512.loc["F56", "mean_loss_db"] / _s13_512.loc["A", "mean_loss_db"]),
    "s13_256_bend_A": _f(_s13_256.loc["A", "mean_bend_loss_db"]),
    "s13_256_bend_F56": _f(_s13_256.loc["F56", "mean_bend_loss_db"]),
    "s13_256_cross_A": _f(_s13_256.loc["A", "mean_crossing_loss_db"]),
    "s13_256_cross_F56": _f(_s13_256.loc["F56", "mean_crossing_loss_db"]),
    "s13_256_angle_A": f"{_s13_256.loc['A', 'mean_bend_total_deg']:.1f}",
    "s13_256_angle_F56": f"{_s13_256.loc['F56', 'mean_bend_total_deg']:.1f}",
    "s13_256_F56_u10": int(_s13_256.loc["F56", "crossings_under_10deg"]),
    "s13_512_F56_u10": int(_s13_512.loc["F56", "crossings_under_10deg"]),
    "s13_512_F56_spacing": int(_s13_512.loc["F56", "spacing_violation_count"]),
    # 最差路线
    "worst_256_A": _f(D.step13_worst_tracking(256).set_index("scheme").loc["A", "total_loss_db"]),
    "worst_256_F56": _f(D.step13_worst_tracking(256).set_index("scheme").loc["F56", "total_loss_db"]),
    "worst_512_A": _f(D.step13_worst_tracking(512).set_index("scheme").loc["A", "total_loss_db"]),
    "worst_512_F56": _f(D.step13_worst_tracking(512).set_index("scheme").loc["F56", "total_loss_db"]),
    # 敏感性（Step 13）
    "sens13_512_F56_x10": _f(_sens13_512[(_sens13_512["scheme"] == "F56") & (_sens13_512["factor"] == 10)]["max_loss_db"].iloc[0]),
    "sens13_256_F56_x10": _f(_sens13_256[(_sens13_256["scheme"] == "F56") & (_sens13_256["factor"] == 10)]["max_loss_db"].iloc[0]),
    # Step 14
    "s14_512_base_mean": _f(_s14_512.loc["base", "mean_loss_db"]),
    "s14_512_base_max": _f(_s14_512.loc["base", "max_loss_db"]),
    "s14_512_opt_mean": _f(_s14_512.loc["opt_base", "mean_loss_db"]),
    "s14_512_opt_p95": _f(_s14_512.loc["opt_base", "p95_loss_db"]),
    "s14_512_opt_max": _f(_s14_512.loc["opt_base", "max_loss_db"]),
    "s14_256_base_mean": _f(_s14_256.loc["base", "mean_loss_db"]),
    "s14_256_base_max": _f(_s14_256.loc["base", "max_loss_db"]),
    "s14_512_opt_max_delta": _f(float(_acc512.loc["opt_base", "max_delta_db"])),
    "s14_512_opt_mean_delta": _f(float(_acc512.loc["opt_base", "mean_delta_db"])),
    "s14_512_opt_improved": int(_margin512.loc["opt_base", "improved_routes"]),
    "s14_512_opt_violations": int(_margin512.loc["opt_base", "violating_routes"]),
    "s14_512_accept": int(_rec_512["accepted"]), "s14_512_tried": int(_rec_512["candidates_tried"]),
    "s14_512_opt_runtime": _f(_rec_512["runtime_s"], 1),
    "s14_256_accept": int(_rec_256["accepted"]), "s14_256_tried": int(_rec_256["candidates_tried"]),
    "s14_256_opt_runtime": _f(_rec_256["runtime_s"], 1),
    "scen512_base": _f(_s14_512.loc["base", "scenario5_max_loss_db"]),
    "scen512_opt": _f(_s14_512.loc["opt_base", "scenario5_max_loss_db"]),
    "scen512_gain": _f(float(_s14_512.loc["base", "scenario5_max_loss_db"] - _s14_512.loc["opt_base", "scenario5_max_loss_db"])),
    "scen512_base10": _f(_scen_512[(_scen_512["scheme"] == "base") & (_scen_512["factor"] == 10)]["max_loss_db"].iloc[0]),
    "scen512_opt10": _f(_scen_512[(_scen_512["scheme"] == "opt_base") & (_scen_512["factor"] == 10)]["max_loss_db"].iloc[0]),
    # 三维
    "d9e_final": f"{_9e['final_collision_pair_count']:,}", "d9e_pct": _f(_9e["reduction_percent"], 2),
    "d9f2_final": f"{_9f2['final_collision_pair_count']:,}", "d9f2_pct": _f(_9f2["reduction_percent"], 2),
    "d9f3_final": f"{_9f3['final_collision_pair_count']:,}", "d9f3_pct": _f(_9f3["reduction_percent"], 2),
    "d10_initial": f"{_10['initial_collision_pairs']:,}", "d10_final": f"{_10['final_collision_pairs']:,}",
    "d10_pct": _f(_10["reduction_percent"], 2), "d10_extra": _f(_10["total_extra_length_mm"], 2),
    "d10_runtime": _f(_10["runtime"]["total_seconds"], 1),
    "d10_elev": _10["successful_elevations"], "d10_transitions": _10["transition_count"],
}


def q(key: str) -> str:
    """取关键数字字符串。"""
    return str(DATA[key])


# ---------------------------------------------------------------------------
# 封面与摘要
# ---------------------------------------------------------------------------

TITLE = "二维与三维光波导自动布线算法的复现、优化与实验验证"
COVER = {
    "school": "电子科技大学",
    "doc_type": "学士学位论文（实验报告）",
    "title": TITLE,
    "author": "李昊伦",
    "student_id": "待填写",
    "major": "待填写",
    "advisor": "待填写",
    "college": "待填写",
    "date": "2026 年 10 月",
}
COVER_NOTES = "作者姓名取自模板文件名；学校名取自格式模板页眉。其余信息请按学校统一封面核实填写。"

def _flatten(text: str) -> str:
    """把多行源码字符串规范为单行（去除换行与缩进空格），避免 Word 段落内出现多余换行。"""
    return " ".join(text.split())


ABSTRACT = _flatten(f"""本报告面向板级光互连中的光波导自动布线问题，在复现原论文布线算法与损耗模型的基础上，
研究二维布线优化与三维层分配扩展，并对全部实验给出统一、可追溯的量化分析。二维部分以 256 与 512 通道
光纤板为对象：首先完成原论文的精确复现，复现几何与原版字节码逐位一致（逐路最大偏差 7.1e-15 dB），
平均与最大损耗相对论文的偏差不超过 1.1%，偏差来源被定位为交叉损耗表的数字化近似；随后在端点、
板面与损耗模型完全一致的条件下，先后开展候选轨道策略（Step 12）、固定端点与自由弯角路径（Step 13）
以及冻结半径与显式保护约束（Step 14）的实验。结果表明：候选轨道选择的收益接近于零；弯曲损耗是
总损耗的主导项；把跨侧连接由 U 型改为自由弯角 S 形并配合自适应半径，可将平均损耗分别降低
{q("s13_256_improve")}（256）与 {q("s13_512_improve")}（512），同时引入可量化的小角交叉与间距代价；
在冻结半径与固定保护对象集合下，512 通道的严格保护优化把全局最大损耗降低 {q("s14_512_opt_max_delta")} dB、
×5 压力情景最大损耗降低 {q("scen512_gain")} dB，而 256 通道在当前候选池中未找到严格口径下的可接受改进。
三维部分以几何指标评估层分配策略：同一 512 布局下两层与三层分别把中心线近距 pair 计数降低
{q("d9f2_pct")}% 与 {q("d9f3_pct")}%，1024 通道合成实例降低 {q("d10_pct")}%，且全部为几何计数，
不构成光学损耗结论。全部结果、图表与审计记录可经单一入口脚本复现。""")

KEYWORDS = "光波导自动布线；损耗优化；自由弯角；冻结半径；稳健优化；层分配"

ABSTRACT_EN = _flatten(f"""This report addresses automatic optical waveguide routing for board-level optical
interconnects. Based on an exact reproduction of the original routing algorithm and loss model, it
studies two-dimensional routing optimization and a three-dimensional layer-assignment extension.
The reproduced geometry matches the original bytecode bit-for-bit, and the mean and maximum loss
deviate from the published values by no more than 1.1%, attributable to the digitized crossing-loss
table. Candidate-track strategies, frozen-endpoint freeform bends, and frozen-radius robust
optimization with an explicit protection set are then evaluated under identical endpoints, board
and loss model. Track selection alone gains almost nothing, while the freeform S-bend geometry with
adaptive radius reduces the mean loss by {q("s13_256_improve")} (256 channels) and
{q("s13_512_improve")} (512 channels), at quantifiable cost in small-angle crossings and spacing
violations. Under frozen radius and a fixed protection set, the strictly accepted 512-channel
result decreases the global maximum loss by {q("s14_512_opt_max_delta")} dB and the x5
stress-scenario maximum by {q("scen512_gain")} dB, whereas no strictly acceptable improvement was
found for 256 channels. In 3D, layer assignment reduces the centerline close-pair count by
{q("d9f2_pct")}% and {q("d9f3_pct")}% for two- and three-layer cases and by {q("d10_pct")}% for a
synthetic 1024-channel instance; these are geometric metrics only and do not constitute optical
loss conclusions.""")

KEYWORDS_EN = "optical waveguide routing; loss optimization; freeform bend; frozen radius; robust optimization; layer assignment"

# ---------------------------------------------------------------------------
# 图元数据（编号、文件、图题、插入宽度）
# ---------------------------------------------------------------------------
# width: full = 版心全宽 150 mm；half = 设计半宽 73 mm（保持原始字号）

FIGURES = {
    "f31": ("3-1", "f31_bend_model_thesis_vs_repro", "90° 弯曲损耗：论文表 3-1 与复刻模型对照", "half"),
    "f32": ("3-2", "f32_reproduction_accuracy", "论文值与复现值对照及有符号相对偏差（256/512/512-R4）", "full"),
    "f33": ("3-3", "f33_radius_sweep_512", "512 通道半径扫描（离散 2/3/4/5 mm）与弯曲损耗占比", "full"),
    "f34": ("3-4", "f34_loss_contribution_repro", "复现损耗分量分解（直线/弯曲/交叉）", "full"),
    "f37": ("3-5", "f37_crossing_angle_distribution", "交叉角度分布与小角放大（256/512）", "full"),
    "f39": ("3-6", "f39_legacy_bytecode_check", "复刻几何与原版字节码的逐路非交叉损耗对照", "full"),
    "f310": ("3-7", "f310_crossing_model_sensitivity", "交叉损耗模型三口径的固定几何复算", "half"),
    "f51": ("4-1", "f51_step12_main", "Step 12 主结果：A–D 方案平均/P95/最大损耗", "full"),
    "f52": ("4-2", "f52_step12_loss_breakdown", "Step 12 损耗分量分解", "full"),
    "f53": ("4-3", "f53_step12_ablation", "Step 12 消融：候选数、顺序、拆线重布、位置正则与半径策略", "full"),
    "f61": ("5-1", "f61_step13_main", "Step 13 补修版主结果：六方案平均/P95/最大损耗", "full"),
    "f62": ("5-2", "f62_step13_breakdown", "Step 13 损耗分量分解：自由弯角以小角交叉换取弯曲收益", "full"),
    "f63": ("5-3", "f63_step13_worst_route", "最差路线跟踪：256 #44 与 512 #287 的六方案对照", "full"),
    "f64": ("5-4", "f64_step13_fix_delta", "补修前后对照：256 F56 的 48 条路线重布", "full"),
    "f65": ("5-5", "f65_step13_constrained", "受约束复算的权衡：间距/小角违规与平均损耗", "full"),
    "f66": ("5-6", "f66_step13_sensitivity", "交叉表压力情景（×1/×2/×5/×10）下的最大损耗", "full"),
    "f71": ("6-1", "f71_step14_main", "Step 14 冻结半径六配置主对照与严格验收状态", "full"),
    "f72": ("6-2", "f72_step14_scenario5", "标称与 ×5 压力情景最大损耗及 opt_base 改善", "full"),
    "f74": ("6-3", "f74_step14_protection_delta", "固定保护对象逐路损耗差值热力图", "full"),
    "f75": ("6-4", "f75_step14_optimize_process", "opt_base 候选接受过程与拒绝原因分布", "full"),
    "f77": ("6-5", "f77_step14_sensitivity", "Step 14 压力情景（×1–×10）与 ×10 情景的边界", "full"),
    "f81": ("7-1", "f81_3d_layer_assignment", "三维层分配结果与近距 pair 净减少", "full"),
    "f83": ("7-2", "f83_3d_fixed_1024", "固定 1024 通道：近距 pair、终态层使用与运行时间分解", "full"),
    "f84": ("7-3", "f84_3d_xy_projection", "1024 通道终态 XY 投影（按层着色）", "full"),
    "f85": ("7-4", "f85_3d_xz_side", "1024 通道终态 XZ 侧视与抬层示例", "full"),
    # 附录
    "f35": ("A-1", "f35_loss_distribution_repro", "逐路损耗分布与累计分布", "full"),
    "f36": ("A-2", "f36_loss_structure_scatter", "损耗—长度与损耗—交叉数散点（含实算相关系数）", "full"),
    "f38": ("A-3", "f38_legacy_geometric_audit", "legacy 512 精确几何审计（物理求交口径）", "full"),
    "f54": ("A-4", "f54_step12_efficiency", "Step 12 效率视角：运行时间—平均损耗", "half"),
    "f67": ("A-5", "f67_step13_penalty_ablation", "间距惩罚强度扫描（0/0.02/0.05）", "full"),
    "f73": ("A-6", "f73_step14_small_angle", "小角度交叉计数（<5°/<10°/<20°）", "full"),
    "f76": ("A-7", "f76_step14_probe_variants", "opt_base 诊断探针变体（非任务口径）", "half"),
    "f80": ("A-8", "f80_3d_probe_9d", "9-D 单路线抬层探针", "full"),
    "f82": ("A-9", "f82_3d_two_vs_three", "两层与三层对照（9-F）", "full"),
    "f86": ("A-10", "f86_3d_overview", "固定 1024 通道三维总览（z 显示放大 ×20）", "full"),
}

# 表格元数据（编号、文件名、表题）
TABLES = {
    "t31": ("3-1", "t31_bend_model_thesis_vs_repro", "90° 弯曲损耗：论文表 3-1 与复刻模型对照"),
    "t32": ("3-2", "t32_reproduction_compare", "论文值与复现值对照（256/512/512-R4）"),
    "t33": ("3-3", "t33_radius_sweep_512", "512 通道半径扫描明细（R=2–5 mm）"),
    "t34": ("3-4", "t34_crossing_model_sensitivity", "512 通道交叉损耗模型三口径敏感性"),
    "t51": ("4-1", "t51_step12_main", "Step 12 主结果：A–D 方案（256/512）"),
    "t52": ("4-2", "t52_step12_ablation", "Step 12 消融：候选数/顺序/拆线重布/位置正则/半径策略"),
    "t61": ("5-1", "t61_step13_main", "Step 13 补修版主结果：固定端点六方案（256/512）"),
    "t62": ("5-2", "t62_step13_cost", "Step 13 收益的代价：交叉、小角、间距与接触"),
    "t63": ("5-3", "t63_step13_constrained", "Step 13 受约束复算：base/spacing/small/both"),
    "t64": ("5-4", "t64_step13_sensitivity", "Step 13 压力情景：交叉损耗放大 ×1/×2/×5/×10"),
    "t71": ("6-1", "t71_step14_main", "Step 14 冻结半径公平对照：六配置与严格验收"),
    "t72": ("6-2", "t72_step14_scenario", "Step 14 ×5 压力情景与固定保护对象余量"),
    "t73": ("6-3", "t73_step14_optimize", "Step 14 优化接受统计与诊断探针"),
    "t74": ("6-4", "t74_step14_sensitivity", "Step 14 压力情景：×1/×2/×5/×10 的最大逐路损耗"),
    "t81": ("7-1", "t81_3d_experiments", "三维实验汇总（几何指标；无光学损耗计算）"),
}

REFERENCES = [
    "黄志杰. 面向板级高速光互连应用的光波导智能排布技术研究[D]. 上海交通大学（学士学位论文）. "
    "（本项目复现对象；PDF 存于工作目录“黄志杰_毕设论文.pdf”）",
    "M. Weigel et al., “Design and Fabrication of Crossing-Free Waveguide Routing Networks Using a "
    "Multi-Layer Polymer-Based Photonic Integration Platform,” Journal of Lightwave Technology, 42(5), "
    "1511–1517 (2024). DOI: 10.1109/JLT.2023.3320908.",
    "M. O. F. Rasel, A. Yamauchi, and T. Ishigure, “Error-Free Three-Dimensional Multimode Crossover "
    "Graded-Index Polymer Waveguides for Board-Level Optical Circuitry,” Journal of Lightwave Technology, "
    "40(19), 6465–6473 (2022). DOI: 10.1109/JLT.2022.3193229.",
    "H. Baghsiahi, K. Wang, and D. R. Selviah, “Optical loss and crosstalk in multimode "
    "photolithographically fabricated polyacrylate polymer waveguide crossings,” Proc. SPIE 8988, "
    "898807 (2014). DOI: 10.1117/12.2039860.",
    "N. Kohmu, M. Ishii, R. Hatai, and T. Ishigure, “90°-bent graded-index core polymer waveguide for a "
    "high-bandwidth-density VCSEL-based optical engine,” Optics Express, 30(3), 4351–4364 (2022). "
    "DOI: 10.1364/OE.446899.",
    "Y. Shi, X. Liu, L. Ma, M. Immonen, L. Zhu, and Z. He, “Optical printed circuit boards with multimode "
    "polymer waveguides and pluggable connectors for high-speed optical interconnects,” Optics Express, "
    "31(17), 27776–27786 (2023). DOI: 10.1364/OE.497184.",
    "X. Xu, X. Liu, M. Immonen, L. Ma, and Z. He, “Investigation on mode dispersion and lamination "
    "stability of multimode polymer waveguides for an optical backplane,” Optics Express, 30(22), "
    "40505–40514 (2022). DOI: 10.1364/OE.472218.",
    "I. Papakonstantinou et al., “Transition, radiation and propagation loss in polymer multimode "
    "waveguide bends,” Optics Express, 15(2), 669–679 (2007). DOI: 10.1364/OE.15.000669.",
    "F. Zhang et al., “Optimization of the interlayer distance for low-loss and low-crosstalk "
    "double-layer polymer optical waveguides,” Optics Express, 31(15), 23754–23766 (2023). "
    "DOI: 10.1364/OE.489977.",
    "F. Martinez Abreu et al., “Polymeric Optical Waveguides: An Approach to Different Manufacturing "
    "Processes,” Applied Sciences, 15, 10644 (2025). DOI: 10.3390/app151910644.",
]

REFERENCES = [_flatten(r) for r in REFERENCES]

REFERENCES_NOTE = ("参考文献题录逐条核验于项目文献审计文档"
                   "（OpticalWaveguideRouter3D/docs/reports/3d_waveguide_literature_physics_audit_v01.md）；"
                   "论文 [1] 为复现对象。")


def table_data(table_id: str):
    """从既有 _data.csv 读取表格原始数据（供正文数字核对）。"""
    import pandas as pd

    filename = TABLES[table_id][1]
    return pd.read_csv(TABLE_DIR / f"{filename}_data.csv", encoding="utf-8-sig")


def figure_path(figure_id: str) -> Path:
    return FIGURE_DIR / f"{FIGURES[figure_id][1]}.png"


def inventory_frame():
    import pandas as pd

    return pd.read_csv(MANIFEST_DIR / "experiment_inventory.csv", encoding="utf-8-sig")
