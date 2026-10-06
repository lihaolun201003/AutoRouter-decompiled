"""booktabs 三线表生成：每个表输出 .tex 与原始精度 _data.csv。

规则：
* 三线表（顶线/表头线/底线），无竖线；单位在表头；
* 同类指标统一小数位；缺失为 --，不适用为 n/a（并在表注说明）；
* 只在严格可比范围内加粗最优值；表注写明优化目标、可行性与排名规则；
* 论文展示的舍入不覆盖原始精度：_data.csv 保留全精度。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

import pubdata as D
import pubstyle as S

TABLE_DIR = S.TABLE_DIR


# ---------------------------------------------------------------------------
# 通用工具
# ---------------------------------------------------------------------------


def _fmt(value, nd=3) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return "--"
    if isinstance(value, str):
        return value
    return f"{value:.{nd}f}"


def _fmt_int(value) -> str:
    if value is None or (isinstance(value, float) and value != value):
        return "--"
    return f"{int(value):,}".replace(",", r"\,")


def _bold_if(condition: bool, text: str) -> str:
    return r"\textbf{" + text + "}" if condition else text


def _tex_escape(text: str) -> str:
    """转义 LaTeX 特殊字符（保护已有的 \\, 千分位标记）。"""
    protected = text.replace(r"\,", "\x00")
    for old, new in (("&", r"\&"), ("%", r"\%"), ("#", r"\#"),
                     ("_", r"\_"), ("$", r"\$")):
        protected = protected.replace(old, new)
    return protected.replace("\x00", r"\,")


def _write(name: str, caption: str, label: str, colspec: str,
           header_rows: list[list[str]], body_rows: list[list[str]],
           notes: list[str], csv_frame: pd.DataFrame) -> None:
    lines = [
        r"% 由 scripts/publication/tables.py 自动生成，请勿手改。",
        r"% 需要宏包：booktabs（\usepackage{booktabs}）",
        r"\begin{table}[htbp]",
        r"  \centering",
        f"  \\caption{{{_tex_escape(caption)}}}",
        f"  \\label{{{label}}}",
        f"  \\begin{{tabular}}{{{colspec}}}",
        r"    \toprule",
    ]
    for row in header_rows:
        lines.append("    " + " & ".join(_tex_escape(c) for c in row) + r" \\")
    lines.append(r"    \midrule")
    for row in body_rows:
        if row and row[0] == r"\midrule":
            lines.append(r"    \midrule")
            continue
        lines.append("    " + " & ".join(_tex_escape(c) for c in row) + r" \\")
    lines.append(r"    \bottomrule")
    lines.append(r"  \end{tabular}")
    if notes:
        lines.append(r"  \par\vspace{2pt}")
        lines.append(r"  \begin{flushleft}\footnotesize")
        for note in notes:
            lines.append("  " + _tex_escape(note) + r" \\")
        lines.append(r"  \end{flushleft}")
    lines.append(r"\end{table}")
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    (TABLE_DIR / f"{name}.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    csv_frame.to_csv(TABLE_DIR / f"{name}_data.csv", index=False, encoding="utf-8-sig")


NOTE_SCOPE = "损耗为解析物理统计口径（交叉事件按每根波导各计一次）；与原版 calc_index 统计口径不同，两者不混用。"


# ---------------------------------------------------------------------------
# T3-1：弯曲模型对照
# ---------------------------------------------------------------------------


def table_bend_model() -> None:
    radii = [2.0, 3.0, 4.0, 5.0, 6.0]
    rows, data = [], []
    for r in radii:
        paper = D.PAPER_VALUES["bend_90_db"][str(int(r))]
        repro = D.bend_model_90_db(r)
        rel = (repro - paper) / paper * 100
        rows.append([f"{r:.0f}", _fmt(paper, 2), _fmt(repro, 4), _fmt(repro - paper, 4), f"{rel:+.2f}"])
        data.append({"radius_mm": r, "thesis_db": paper, "repro_db": repro,
                     "abs_diff_db": repro - paper, "rel_diff_pct": rel})
    _write(
        "t31_bend_model_thesis_vs_repro",
        "90° 弯曲损耗：论文表 3-1 与复刻模型对照",
        "tab:bend-thesis",
        "rrrrr",
        [["弯曲半径 (mm)", "论文值 (dB)", "复刻值 (dB)", "绝对差 (dB)", "相对差 (%)"]],
        rows,
        ["论文值来自论文表 3-1（R=2/3/4/5/6 mm，几何离散点）；复刻值由原版 tl/ll 弯曲损耗表推得的密度乘以弧长计算。",
         "复刻与论文的相对差均在 ±0.3% 内。"],
        pd.DataFrame(data),
    )


# ---------------------------------------------------------------------------
# T3-2：三个复现 case 对照
# ---------------------------------------------------------------------------


def table_repro_compare() -> None:
    cases = [("256", "256 通道 R5（论文 4.2）", "256_R5"),
             ("512", "512 通道 R5（论文 4.1）", "512_R5"),
             ("512_R4", "512 通道 R4（论文 4.3）", "512_R4")]
    rows, data = [], []
    for key, label, tag in cases:
        paper = D.PAPER_VALUES["cases"][key]
        summary = D.repro_summary(tag)
        for metric, short, field, paper_field in (
                ("平均损耗", "平均", "mean_loss_db", "mean_loss_db"),
                ("最大损耗", "最大", "max_loss_db", "max_loss_db")):
            repro = summary[field]
            paper_value = paper[paper_field]
            rel = (repro - paper_value) / paper_value * 100
            rows.append([label if metric == "平均损耗" else "", short,
                         _fmt(paper_value, 2), _fmt(repro, 4), _fmt(repro - paper_value, 4),
                         f"{rel:+.2f}"])
            data.append({"case": key, "metric": metric, "thesis_db": paper_value,
                         "repro_db": repro, "abs_diff_db": repro - paper_value,
                         "rel_diff_pct": rel})
    _write(
        "t32_reproduction_compare",
        "论文值与复现值对照（256/512/512-R4）",
        "tab:repro-compare",
        "llrrrr",
        [["复现 case", "指标", "论文值 (dB)", "复现值 (dB)", "绝对差 (dB)", "相对差 (%)"]],
        rows,
        ["论文值来自论文 4.1/4.2/4.3 节；复现值取自 OpticalWaveguideRouter2D/results 的逐路损耗明细汇总。",
         "复现几何与原版布线逐位一致（原版字节码对照），差异来自交叉损耗表的数字化近似。"],
        pd.DataFrame(data),
    )


# ---------------------------------------------------------------------------
# T3-3：半径扫描
# ---------------------------------------------------------------------------


def table_radius_sweep() -> None:
    rows, data = [], []
    for tag, radius in [("512_R2", 2), ("512_R3", 3), ("512_R4", 4), ("512_R5", 5)]:
        summary = D.repro_summary(tag)
        frame = D.repro_route_frame(tag)
        p95 = D.repro_percentile(tag, 95)
        rows.append([str(radius), _fmt(summary["mean_loss_db"], 4), _fmt(p95, 4),
                     _fmt(summary["max_loss_db"], 4),
                     _fmt(summary["mean_straight_loss_db"], 3),
                     _fmt(summary["mean_bend_loss_db"], 3),
                     _fmt(summary["mean_crossing_loss_db"], 3),
                     f"{summary['loss_contribution']['bend'] * 100:.1f}",
                     _fmt(summary["mean_total_length_mm"], 2),
                     f"{summary['mean_crossing_count']:.2f}"])
        data.append({"radius_mm": radius, "mean_loss_db": summary["mean_loss_db"],
                     "p95_loss_db": p95, "max_loss_db": summary["max_loss_db"],
                     "mean_straight_loss_db": summary["mean_straight_loss_db"],
                     "mean_bend_loss_db": summary["mean_bend_loss_db"],
                     "mean_crossing_loss_db": summary["mean_crossing_loss_db"],
                     "bend_share_pct": summary["loss_contribution"]["bend"] * 100,
                     "mean_total_length_mm": summary["mean_total_length_mm"],
                     "mean_crossing_count": summary["mean_crossing_count"]})
    _write(
        "t33_radius_sweep_512",
        "512 通道半径扫描（固定几何复算，R=2–5 mm）",
        "tab:radius-sweep",
        "rrrrrrrrrr",
        [["R (mm)", "平均损耗 (dB)", "P95 (dB)", "最大损耗 (dB)", "直线 (dB)", "弯曲 (dB)",
          "交叉 (dB)", "弯曲占比 (%)", "平均总长 (mm)", "平均交叉数"]],
        rows,
        ["同一布线的固定几何复算：只更换弯曲半径并重算损耗，不重新布线；论文 4.3 节只印出 R=4 mm（9.8/11.0 dB），复现为 9.8096/10.9815 dB。",
         "P95 为本次分析由逐路数据实算（n=512）。",
         NOTE_SCOPE],
        pd.DataFrame(data),
    )


# ---------------------------------------------------------------------------
# T5-1：Step 12 主表
# ---------------------------------------------------------------------------


def table_step12_main() -> None:
    rows, data = [], []
    for ch in (256, 512):
        for label in D.step12_comparison(ch)["label"]:
            frame = D.step12_comparison(ch).set_index("label")
            row = frame.loc[label]
            scheme = label.split("-")[0]
            complete = "是" if row["complete_connection"] else "否"
            rows.append([scheme, _fmt(row["mean_loss_db"], 4), _fmt(row["p95_loss_db"], 4),
                         _fmt(row["max_loss_db"], 4), _fmt_int(row["unplaced_count"]),
                         _fmt_int(row["unique_crossing_events"]),
                         _fmt_int(row["spacing_violation_count"]),
                         _fmt(row["runtime_s"], 1), complete])
            data.append({"channels": ch, "scheme": scheme, "mean_loss_db": row["mean_loss_db"],
                         "p95_loss_db": row["p95_loss_db"], "max_loss_db": row["max_loss_db"],
                         "unplaced_count": row["unplaced_count"],
                         "unique_crossing_events": row["unique_crossing_events"],
                         "spacing_violation_count": row["spacing_violation_count"],
                         "runtime_s": row["runtime_s"], "complete": row["complete_connection"]})
        if ch == 256:
            rows.append([r"\midrule"])
    _write(
        "t51_step12_main",
        "Step 12 主结果：A–D 方案（256/512 通道）",
        "tab:step12-main",
        "lrrrrrrrl",
        [["方案", "平均损耗 (dB)", "P95 (dB)", "最大损耗 (dB)", "未布通", "唯一交叉",
          "间距违规", "运行 (s)", "完整连接"]],
        rows,
        ["A=原版 R5；B=统一 R6（参数对照，非算法贡献）；C=候选轨道优化（R5）；D=自适应半径（R5/R6）。",
         "512 的 B 有 2 条未布通，其损耗均值与完整连接的方案不可直接比较；排名只在完整连接的方案间进行。",
         "最优值加粗仅在同一规模、同一完整性条件的行内比较。",
         NOTE_SCOPE],
        pd.DataFrame(data),
    )


# ---------------------------------------------------------------------------
# T5-2：Step 12 消融
# ---------------------------------------------------------------------------


def table_step12_ablation() -> None:
    rows, data = [], []
    for group, keys in D_ABLATION_GROUPS:
        for key in keys:
            line = {"配置组": group, "config": key}
            cells = []
            for ch in (256, 512):
                frame = D.step12_sensitivity_frame(ch).set_index("config")
                row = frame.loc[key]
                line[f"mean_{ch}"] = row["mean_loss_db"]
                line[f"unplaced_{ch}"] = int(row["unplaced_count"])
                line[f"runtime_{ch}"] = row["runtime_s"]
                cells += [_fmt(row["mean_loss_db"], 4), _fmt_int(row["unplaced_count"])]
            rows.append([key] + cells)
            data.append(line)
    _write(
        "t52_step12_ablation",
        "Step 12 消融：候选数/顺序/拆线重布/位置正则/半径策略",
        "tab:step12-ablation",
        "lrrrr",
        [["配置", "256 平均损耗 (dB)", "256 未布通", "512 平均损耗 (dB)", "512 未布通"]],
        rows,
        ["默认配置为 K=8、legacy 顺序、位置正则 0.001（256）/0.01（512）dB/位；候选数消融取 1/4/8/16。",
         "含未布通的配置（顺序 span/congestion、正则 0、512 的固定 R6）损耗均值不能与完整布通配置同口径比较，故不参与排名。",
         NOTE_SCOPE],
        pd.DataFrame(data),
    )


D_ABLATION_GROUPS = [
    ("候选数 K", ["cand_k1", "cand_k4", "cand_k8", "cand_k16"]),
    ("布线顺序", ["order_span", "order_congestion"]),
    ("拆线重布", ["refine_on"]),
    ("位置正则", ["penalty_0", "penalty_0.001", "penalty_0.01", "penalty_0.05"]),
    ("半径策略", ["radius_fixed_R6", "radius_adaptive"]),
]


# ---------------------------------------------------------------------------
# T6-1：Step 13 主表与代价
# ---------------------------------------------------------------------------


def table_step13_main() -> None:
    rows, data = [], []
    for ch in (256, 512):
        frame = D.step13_comparison(ch, fixed=True).set_index("scheme")
        for scheme in ["A", "R5U", "D0", "D56", "F5", "F56"]:
            row = frame.loc[scheme]
            rows.append([scheme, _fmt(row["mean_loss_db"], 4), _fmt(row["p95_loss_db"], 4),
                         _fmt(row["max_loss_db"], 4), _fmt(row["mean_straight_loss_db"], 4),
                         _fmt(row["mean_bend_loss_db"], 4), _fmt(row["mean_crossing_loss_db"], 4)])
            data.append({"channels": ch, "scheme": scheme,
                         "mean_loss_db": row["mean_loss_db"], "p95_loss_db": row["p95_loss_db"],
                         "max_loss_db": row["max_loss_db"],
                         "mean_straight_loss_db": row["mean_straight_loss_db"],
                         "mean_bend_loss_db": row["mean_bend_loss_db"],
                         "mean_crossing_loss_db": row["mean_crossing_loss_db"]})
        rows.append([r"\midrule"])
    rows.pop()
    _write(
        "t61_step13_main",
        "Step 13 补修后主结果：固定端点六方案（256/512）",
        "tab:step13-main",
        "lrrrrrr",
        [["方案", "平均损耗 (dB)", "P95 (dB)", "最大损耗 (dB)", "直线 (dB)", "弯曲 (dB)", "交叉 (dB)"]],
        rows,
        ["A=原版几何（端点来源）；R5U=固定端点+U 型+R5；D0=优先 R6 回退 R5；D56=自适应 R5/R6；F5/F56=自由弯角（半径 R5 / R5+R6）。",
         "全部方案端点冻结（endpoint_changes=0），D56/F56 为本次补修后（256 的 F56 已重布历史重合对 #7/#31）。",
         "自由弯角方案以更高的交叉损耗换取更低的弯曲损耗（见分解列），最优值加粗仅在同列六方案内。",
         NOTE_SCOPE],
        pd.DataFrame(data),
    )


def table_step13_cost() -> None:
    rows, data = [], []
    for ch in (256, 512):
        frame = D.step13_comparison(ch, fixed=True).set_index("scheme")
        for scheme in ["A", "R5U", "D0", "D56", "F5", "F56"]:
            row = frame.loc[scheme]
            rows.append([scheme, _fmt_int(row["unique_crossing_events"]),
                         _fmt_int(row["crossings_under_10deg"]),
                         _fmt(row["min_crossing_angle_deg"], 2),
                         _fmt_int(row["spacing_violation_count"]),
                         _fmt_int(row["contact_touch_count"]),
                         _fmt_int(row["contact_overlap_count"]),
                         _fmt(row["mean_bend_total_deg"], 1)])
            data.append({"channels": ch, "scheme": scheme,
                         "unique_crossing_events": row["unique_crossing_events"],
                         "crossings_under_10deg": row["crossings_under_10deg"],
                         "min_crossing_angle_deg": row["min_crossing_angle_deg"],
                         "spacing_violation_count": row["spacing_violation_count"],
                         "contact_touch_count": row["contact_touch_count"],
                         "contact_overlap_count": row["contact_overlap_count"],
                         "mean_bend_total_deg": row["mean_bend_total_deg"]})
        rows.append([r"\midrule"])
    rows.pop()
    _write(
        "t62_step13_cost",
        "Step 13 收益的代价：交叉、小角、间距与接触（256/512）",
        "tab:step13-cost",
        "lrrrrrrr",
        [["方案", "唯一交叉", "<10° 交叉", "最小交叉角 (°)", "间距违规", "段级接触", "重合", "平均转角 (°)"]],
        rows,
        ["段级接触为解析段接缝的原始计数（含重复），未经整条路线合并；重合（overlap）为零表示无物理重合。",
         "自由弯角把平均总转角从约 170° 降到约 100°，同时 <10° 交叉从 0 增至 150（256）/842（512）。",
         "间距阈值为实验假设（线宽+标称间隔），原版无显式间距规则。"],
        pd.DataFrame(data),
    )


# ---------------------------------------------------------------------------
# T6-2：受约束实验
# ---------------------------------------------------------------------------


def table_step13_constrained() -> None:
    rows, data = [], []
    for ch in (256, 512):
        frame = D.step13_constrained(ch).set_index("config")
        for config in ["base", "spacing", "small", "both"]:
            row = frame.loc[config]
            rows.append([config, _fmt(row["mean_loss_db"], 4), _fmt(row["max_loss_db"], 4),
                         _fmt_int(row["crossings_under_5_deg"]), _fmt_int(row["crossings_under_10_deg"]),
                         _fmt_int(row["crossings_under_20_deg"]), _fmt_int(row["spacing_violation_count"]),
                         _fmt_int(row["contact_touch_count"])])
            data.append({"channels": ch, "config": config, "mean_loss_db": row["mean_loss_db"],
                         "max_loss_db": row["max_loss_db"],
                         "crossings_under_5_deg": row["crossings_under_5_deg"],
                         "crossings_under_10_deg": row["crossings_under_10_deg"],
                         "crossings_under_20_deg": row["crossings_under_20_deg"],
                         "spacing_violation_count": row["spacing_violation_count"],
                         "contact_touch_count": row["contact_touch_count"]})
        rows.append([r"\midrule"])
    rows.pop()
    _write(
        "t63_step13_constrained",
        "Step 13 受约束复算：base/spacing/small/both（几何不变，仅改评分）",
        "tab:step13-constrained",
        "lrrrrrrr",
        [["配置", "平均损耗 (dB)", "最大损耗 (dB)", "<5° 交叉", "<10° 交叉", "<20° 交叉", "间距违规", "段级接触"]],
        rows,
        ["本组实验在固定几何（F56）上仅改变评分权重，不改变半径与端点：spacing=0.05 dB/路线对；small=<20° 每事件 0.05 dB；both 同时启用。",
         "256 的 base 子目录内容即 F56 几何；与 Step 14 的对照实验不同（Step 14 同时冻结半径），两者条件不可混用。"],
        pd.DataFrame(data),
    )


# ---------------------------------------------------------------------------
# T6-3：Step 13 交叉表敏感性
# ---------------------------------------------------------------------------


def table_step13_sensitivity() -> None:
    rows, data = [], []
    for ch in (256, 512):
        frame = D.step13_fix_sensitivity(ch)
        for scheme in ["A", "R5U", "D0", "D56", "F5", "F56"]:
            sub = frame[frame["scheme"] == scheme].set_index("factor")
            cells = []
            for factor in (1, 2, 5, 10):
                cells.append(_fmt(sub.loc[factor, "max_loss_db"], 4))
            rows.append([scheme] + cells)
            data.append({"channels": ch, "scheme": scheme,
                         "max_x1": sub.loc[1, "max_loss_db"], "max_x2": sub.loc[2, "max_loss_db"],
                         "max_x5": sub.loc[5, "max_loss_db"], "max_x10": sub.loc[10, "max_loss_db"]})
        rows.append([r"\midrule"])
    rows.pop()
    _write(
        "t64_step13_sensitivity",
        "Step 13 压力情景：交叉损耗放大 ×1/×2/×5/×10 的最大逐路损耗",
        "tab:step13-sensitivity",
        "lrrrr",
        [["方案", "×1 (dB)", "×2 (dB)", "×5 (dB)", "×10 (dB)"]],
        rows,
        ["固定几何复算：仅把 <20° 区间交叉损耗放大，再重算全部逐路损耗；不重新布线，路线选择不变。",
         "×5/×10 是实验压力情景，不代表已验证的真实物理误差范围。"],
        pd.DataFrame(data),
    )


# ---------------------------------------------------------------------------
# T7-1：Step 14 主表 + 验收
# ---------------------------------------------------------------------------


def _reason_zh(reason: str) -> str:
    names = {
        "mean_budget_exceeded": "均值预算超限",
        "max_worse": "全局最大劣化",
        "scenario_not_improved": "情景无改善",
    }
    if reason in names:
        return names[reason]
    if reason.startswith("protected_worse_"):
        return "保护对象 #" + reason.split("_")[-1] + " 劣化"
    return reason


def table_step14_main() -> None:
    acceptance = {ch: D.step14_acceptance(ch).set_index("scheme") for ch in (256, 512)}
    rows, data = [], []
    for ch in (256, 512):
        frame = D.step14_comparison(ch).set_index("scheme")
        for scheme in S.STEP14_SCHEMES:
            row = frame.loc[scheme]
            acc = acceptance[ch].loc[scheme]
            ok = "通过" if acc["ok"] else "未通过"
            reason = "" if acc["ok"] else _reason_zh(str(acc["reasons"]).split(";")[0]) + " 等"
            rows.append([scheme, _fmt(row["mean_loss_db"], 4), _fmt(row["p95_loss_db"], 4),
                         _fmt(row["max_loss_db"], 4), _fmt_int(row["spacing_violation_count"]),
                         _fmt_int(row["physical_route_touch_count"]),
                         f"{ok}", reason])
            data.append({"channels": ch, "scheme": scheme, "mean_loss_db": row["mean_loss_db"],
                         "p95_loss_db": row["p95_loss_db"], "max_loss_db": row["max_loss_db"],
                         "spacing_violation_count": row["spacing_violation_count"],
                         "physical_route_touch_count": row["physical_route_touch_count"],
                         "accept_ok": bool(acc["ok"]), "accept_reasons": acc["reasons"]})
        rows.append([r"\midrule"])
    rows.pop()
    _write(
        "t71_step14_main",
        "Step 14 冻结半径公平对照：六配置与严格验收",
        "tab:step14-main",
        "lrrrrrll",
        [["配置", "平均损耗 (dB)", "P95 (dB)", "最大损耗 (dB)", "间距违规", "物理接触", "严格验收", "首个未通过原因"]],
        rows,
        ["全部配置在 F56 逐路半径冻结下运行；验收规则：完整连接、零重合/几何违规、均值 ≤ base+0.05 dB、全局最大 ≤ base、11 条固定保护对象逐路不劣化、压力情景最大严格下降。",
         "touch 配置与 base 逐项相同（物理接触数为 0，惩罚无作用对象）。",
         "未通过验收的配置仍展示，但不作为最终推荐；opt_base 为唯一通过严格验收的优化结果。"],
        pd.DataFrame(data),
    )


# ---------------------------------------------------------------------------
# T7-2：压力情景 + 保护余量
# ---------------------------------------------------------------------------


def table_step14_scenario() -> None:
    rows, data = [], []
    for ch in (256, 512):
        frame = D.step14_comparison(ch).set_index("scheme")
        margin = D.step14_margins(ch).set_index("scheme")
        for scheme in S.STEP14_SCHEMES:
            row = frame.loc[scheme]
            mrow = margin.loc[scheme]
            rows.append([scheme, _fmt(row["scenario5_mean_loss_db"], 4),
                         _fmt(row["scenario5_max_loss_db"], 4),
                         _fmt(mrow["max_violation_db"], 4),
                         _fmt_int(mrow["violating_routes"]),
                         _fmt_int(mrow["improved_routes"])])
            data.append({"channels": ch, "scheme": scheme,
                         "scenario5_mean_loss_db": row["scenario5_mean_loss_db"],
                         "scenario5_max_loss_db": row["scenario5_max_loss_db"],
                         "max_violation_db": mrow["max_violation_db"],
                         "violating_routes": mrow["violating_routes"],
                         "improved_routes": mrow["improved_routes"]})
        rows.append([r"\midrule"])
    rows.pop()
    _write(
        "t72_step14_scenario",
        "Step 14 ×5 压力情景与固定保护对象余量",
        "tab:step14-scenario",
        "lrrrrr",
        [["配置", "情景平均 (dB)", "情景最大 (dB)", "保护最大劣化 (dB)", "劣化对象数", "改善对象数"]],
        rows,
        ["压力情景=<20° 交叉损耗 ×5（固定几何复算）；保护对象为 Step 14 保存的 11 条固定 ID 集合，所有配置使用同一集合。",
         "opt_base 在 256 与 512 上均实现保护对象零劣化与情景最大损耗严格下降。"],
        pd.DataFrame(data),
    )


# ---------------------------------------------------------------------------
# T7-3：接受过程与诊断
# ---------------------------------------------------------------------------


def table_step14_optimize() -> None:
    rows, data = [], []
    for ch in (256, 512):
        record = D.step14_optimize_record(ch)["opt_base"]
        rows.append(["opt_base（%d）" % ch, _fmt_int(record["candidates_tried"]),
                     _fmt_int(record["accepted"]), _fmt(record["runtime_s"], 1),
                     _fmt_int(record["rollback_fingerprint_mismatches"])])
        data.append({"channels": ch, "variant": "opt_base",
                     "candidates_tried": record["candidates_tried"],
                     "accepted": record["accepted"], "runtime_s": record["runtime_s"],
                     "rollback_mismatches": record["rollback_fingerprint_mismatches"]})
        probe = D.step14_probe_summary(ch)
        for _, prow in probe.iterrows():
            rows.append([f"{prow['variant']}（{ch}）", _fmt_int(prow["candidates_tried"]),
                         _fmt_int(prow["accepted"]), _fmt(prow["runtime_s"], 1),
                         _fmt_int(prow["rollback_fingerprint_mismatches"])])
            data.append({"channels": ch, "variant": prow["variant"],
                         "candidates_tried": prow["candidates_tried"],
                         "accepted": prow["accepted"], "runtime_s": prow["runtime_s"],
                         "rollback_mismatches": prow["rollback_fingerprint_mismatches"]})
        rows.append([r"\midrule"])
    rows.pop()
    _write(
        "t73_step14_optimize",
        "Step 14 优化接受统计与诊断探针",
        "tab:step14-optimize",
        "lrrrr",
        [["变体", "候选尝试", "接受", "运行 (s)", "回滚指纹不一致"]],
        rows,
        ["opt_base 为任务口径（严格验收）：256 接受 0 个候选（当前候选池中未找到可接受改进）、512 接受 6 个。",
         "rank_small*（加严候选排序）与 strict_slack*（保护余量放宽 0.01/0.05 dB）为诊断口径，不代表任务验收规则。",
         "回滚指纹不一致为 0 表示每次拒绝都完整回滚并核对状态一致。"],
        pd.DataFrame(data),
    )


# ---------------------------------------------------------------------------
# T3-4：交叉模型敏感性
# ---------------------------------------------------------------------------


def table_crossing_model_sensitivity() -> None:
    """512 R5 三种交叉损耗口径的固定几何复算（主口径 B 与文档记录一致）。"""
    scopes = D.crossing_sensitivity()
    rows, data = [], []
    for key in ("A", "B", "C"):
        entry = scopes[key]
        rows.append([key, entry["note"], _fmt(entry["mean"], 4), _fmt(entry["max"], 4)])
        data.append({"scope": key, "note": entry["note"], "mean_loss_db": entry["mean"],
                     "max_loss_db": entry["max"]})
    _write(
        "t34_crossing_model_sensitivity",
        "512 通道交叉损耗模型的敏感性（固定几何复算）",
        "tab:crossing-sensitivity",
        "llrr",
        [["口径", "说明", "平均损耗 (dB)", "最大损耗 (dB)"]],
        rows,
        ["三种口径均为固定几何复算（不改布线）：非交叉部分相同，只替换交叉项；逐路交叉条目按每根波导各计一次。",
         "与 OpticalWaveguideRouter2D/docs/loss_model_reconstruction_report.md 第 7 节的记录值（均值 5.4758/5.5147/5.5745 与最大 6.5224/6.5761/6.6659）一致（±0.002 dB，差异来自文档记录的四位舍入）。",
         "主口径（B）即全部复现图的损耗口径。"],
        pd.DataFrame(data),
    )


# ---------------------------------------------------------------------------
# T8：三维实验汇总
# ---------------------------------------------------------------------------


def table_3d_experiments() -> None:
    nine_e = D.step9e_summary()
    two = D.step9f_two_layer_summary()
    three = D.step9f_three_layer_summary()
    ten = D.step10_summary()
    rows, data = [], []

    def add(name, scale, layers, attempts, success, initial, final, extra, runtime):
        rows.append([name, str(layers), _fmt_int(attempts), _fmt_int(success),
                     f"{_fmt_int(initial)} → {_fmt_int(final)}",
                     _fmt(extra, 2), _fmt(runtime, 1)])
        data.append({"experiment": name, "scale": scale, "layers": layers,
                     "attempts": attempts, "successful_elevations": success,
                     "initial_pairs": initial, "final_pairs": final,
                     "extra_length_mm": extra, "runtime_s": runtime})

    add("9-E 顺序层分配（512）", 512, 2, nine_e["target_attempts"], nine_e["successful_elevations"],
        nine_e["initial_collision_pair_count"], nine_e["final_collision_pair_count"],
        nine_e["total_extra_length_mm"], nine_e["runtime_seconds"])
    add("9-F 两层对照（512）", 512, 2, two["target_attempts"], two["successful_elevations"],
        two["initial_collision_pair_count"], two["final_collision_pair_count"],
        two["total_extra_length_mm"], two["runtime_seconds"])
    add("9-F 三层（512）", 512, 3, three["target_attempts"], three["successful_elevations"],
        three["initial_collision_pair_count"], three["final_collision_pair_count"],
        three["total_extra_length_mm"], three["runtime_seconds"])
    add("10 固定 1024（1024，合成实例）", 1024, 3, ten["target_attempts"], ten["successful_elevations"],
        ten["initial_collision_pairs"], ten["final_collision_pairs"],
        ten["total_extra_length_mm"], ten["runtime"]["total_seconds"])
    _write(
        "t81_3d_experiments",
        "三维实验汇总（几何指标；无光学损耗计算）",
        "tab:3d-experiments",
        "lrrrrrr",
        [["实验（规模）", "层数", "尝试", "成功抬层", "近距 pair（初 → 终）",
          "额外长度 (mm)", "运行 (s)"]],
        rows,
        ["近距 pair=自定义中心线 clearance<0.1 mm 的路线对数；不是制造违规数，也不是光学风险指标。",
         "9-E 目标 30 次 attempt、9-F 两组各 50 次、Step 10 上限 1024 次；三次实验的初始 pair 均为 49 518（512 布局）/204 291（1024 实例）。",
         "全部实验为几何/算法指标，项目未建立三维光学损耗模型，不得据此推断损耗改善。"],
        pd.DataFrame(data),
    )


def table_step14_sensitivity() -> None:
    rows, data = [], []
    for ch in (256, 512):
        frame = D.step14_sensitivity(ch)
        for scheme in S.STEP14_SCHEMES:
            sub = frame[frame["scheme"] == scheme].set_index("factor")
            rows.append([scheme,
                         _fmt(sub.loc[1, "max_loss_db"], 4), _fmt(sub.loc[2, "max_loss_db"], 4),
                         _fmt(sub.loc[5, "max_loss_db"], 4), _fmt(sub.loc[10, "max_loss_db"], 4)])
            data.append({"channels": ch, "scheme": scheme,
                         "max_x1": sub.loc[1, "max_loss_db"], "max_x2": sub.loc[2, "max_loss_db"],
                         "max_x5": sub.loc[5, "max_loss_db"], "max_x10": sub.loc[10, "max_loss_db"]})
        rows.append([r"\midrule"])
    rows.pop()
    _write(
        "t74_step14_sensitivity",
        "Step 14 压力情景：交叉损耗放大 ×1/×2/×5/×10 的最大逐路损耗",
        "tab:step14-sensitivity",
        "lrrrr",
        [["配置", "×1 (dB)", "×2 (dB)", "×5 (dB)", "×10 (dB)"]],
        rows,
        ["固定几何复算；512 的 opt_base 在 ×10 由 8.4333 升至 8.4996 dB（如实记录为略恶化），×1–×5 均下降。",
         "×5/×10 是实验压力情景，不代表已验证的真实物理误差范围。"],
        pd.DataFrame(data),
    )


ALL = [
    table_bend_model,
    table_repro_compare,
    table_radius_sweep,
    table_crossing_model_sensitivity,
    table_step12_main,
    table_step12_ablation,
    table_step13_main,
    table_step13_cost,
    table_step13_constrained,
    table_step13_sensitivity,
    table_step14_main,
    table_step14_scenario,
    table_step14_optimize,
    table_step14_sensitivity,
    table_3d_experiments,
]


def generate() -> None:
    for func in ALL:
        func()
        print(f"  [表格] {func.__name__} 完成", flush=True)
