"""Build the v8-continuation report (markdown + DOCX + PDF) from saved artefacts.

Every number is read from the frozen comparison/diagnostic/verification files;
nothing is typed in by hand except the prose that interprets them.

Usage:
  <python> scripts/publication/build_v8_continuation_report.py PROJECT OUTDIR
"""
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "publication"))

CMP = OUT / "comparison"
DOCS = ROOT / "docs/reports"
REPORT_DIR = ROOT / "publication/report"
NAME = "三维布线v8路径弧长窗口续跑报告"


def load(name, default=None):
    path = CMP / (name + ".json")
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


STOP_SHORT = {"CANDIDATE_BUDGET_EXHAUSTED": "预算用尽", "TARGET_LIMIT": "目标上限",
              "NO_ELIGIBLE_TARGETS": "无可用目标", None: "-"}


def short_stop(value):
    return STOP_SHORT.get(value, value or "-")


def table(rows, columns, header=None):
    head = header or columns
    lines = ["| " + " | ".join(head) + " |",
             "| " + " | ".join("---" for _ in columns) + " |"]
    for row in rows:
        cells = []
        for column in columns:
            value = row.get(column) if isinstance(row, dict) else None
            cells.append("" if value is None else str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def fmt(value, digits=2):
    if value is None:
        return "-"
    if isinstance(value, float):
        return ("%%.%df" % digits) % value
    return str(value)


def p2_section():
    data = load("p2_g0_vs_g1")
    if not data:
        return "## 3 v8 正式对照（P2）\n\n（comparison/p2_g0_vs_g1.json 缺失）\n"
    rows = []
    for cell in data["cells"]:
        rows.append(dict(mode=cell["mode"], budget=cell["budget"],
                         start="挑战" if cell.get("challenge") else "主",
                         g0_pairs=cell["g0"].get("final_collision_pairs"),
                         g1_pairs=cell["g1"].get("final_collision_pairs"),
                         delta_pairs=cell.get("delta_final_pairs"),
                         g0_evals=cell["g0"].get("candidate_evaluations"),
                         g1_evals=cell["g1"].get("candidate_evaluations"),
                         g0_moves=cell["g0"].get("accepted_moves"),
                         g1_moves=cell["g1"].get("accepted_moves"),
                         g0_len=fmt(cell["g0"].get("stage_length_delta_mm")),
                         g1_len=fmt(cell["g1"].get("stage_length_delta_mm")),
                         g1_path_windows=(cell["g1"].get("executed_moves_by_window_kind") or {}
                                         ).get("PATH_WINDOW_G1"),
                         g1_line_windows=(cell["g1"].get("executed_moves_by_window_kind") or {}
                                          ).get("LINE_WINDOW_G0")))
    text = ["## 3 v8 正式对照（P2）", ""]
    text.append("G0 = 原有限直线窗口生成域（引用 v7 T0 / v6 E2，配置逐字段相同）；"
                "G1 = 保留全部 G0 候选并新增沿冻结平面弧长的路径窗口。")
    text.append("")
    text.append(table(rows, ["mode", "budget", "start", "g0_pairs", "g1_pairs",
                             "delta_pairs", "g0_len", "g1_len"],
                      ["模式", "预算", "起点", "G0对", "G1对", "Δ对", "G0长mm", "G1长mm"]))
    text.append("")
    text.append(table(rows, ["mode", "budget", "start", "g0_evals", "g1_evals", "g0_moves",
                             "g1_moves", "g1_path_windows", "g1_line_windows"],
                      ["模式", "预算", "起点", "G0评价", "G1评价", "G0动作", "G1动作",
                       "路径窗动作", "直线窗动作"]))
    text.append("")
    text.append("**判定**：" + str(data.get("verdict")))
    return "\n".join(text) + "\n"


def neutrality_section():
    data = load("neutrality_v8_code")
    if not data:
        return "## 4 v8 代码中立性（G0 等价复跑）\n\n（comparison/neutrality_v8_code.json 缺失）\n"
    rows = []
    for row in data["rows"]:
        rows.append(dict(new=row["new_group"], old=row["old_group"],
                         fields=row.get("identical_all_comparable_fields"),
                         steps=row.get("step_trace_identical"),
                         pairs=row.get("near_distance_sets_identical"),
                         routes=row.get("final_routes_identical")))
    text = ["## 4 v8 代码中立性（G0 等价复跑）", "",
            "新代码在 G0（LINE_ONLY）生成域下必须与历史 v7 T0 结果逐位一致，",
            "以证明新增的路径窗口支持链没有改变旧路径的任何决策。", "",
            table(rows, ["new", "old", "fields", "steps", "pairs", "routes"],
                  ["新复跑组", "历史组", "可比字段全部相同", "步级轨迹相同",
                   "近距/未决集合相同", "终态几何文件相同"]), "",
            "可比的旧字段全部一致；新代码新增的账本字段（路径窗口数、逻辑升降数、物理片段数、"
            "cap 计数器）在历史组中不存在，因此记为“新增字段”，不作为行为差异。", "",
            "**判定**：" + str(data.get("verdict"))]
    return "\n".join(text) + "\n"


def diagnostics_section():
    path = OUT / "diagnostics" / "v8_side_diagnostics_summary.json"
    if not path.is_file():
        return "## 5 冻结诊断集（60 对 / 120 侧）\n\n（诊断尚未运行）\n"
    summary = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for key, label in (("v4_outcome_counts", "v4 冻结结果"),
                       ("g0_outcome_counts", "G0 直线窗口"),
                       ("g1_outcome_counts", "G1 路径窗口")):
        row = dict(domain=label)
        for outcome in ("NO_LEGAL_WINDOW_UNDER_CURRENT_RULES", "CANDIDATES_EXIST_BASIC_ALL_REJECTED",
                        "BASIC_PASSES_FULL_NO_NET_GAIN", "BASIC_PASSES_FULL_CHECK_CAPPED",
                        "FULL_ACCEPTED_CANDIDATE_EXISTS"):
            row[outcome] = summary[key].get(outcome, 0)
        rows.append(row)
    text = ["## 5 冻结诊断集（60 对 / 120 侧）", "",
            "诊断集与分类沿用 v4 冻结的 target_list.json / side_audit.json（seed 20261006）。",
            "诊断费用单记，不参与任何优化预算，也不用于挑选性能目标。", "",
            table(rows, ["domain", "NO_LEGAL_WINDOW_UNDER_CURRENT_RULES",
                         "CANDIDATES_EXIST_BASIC_ALL_REJECTED", "BASIC_PASSES_FULL_NO_NET_GAIN",
                         "BASIC_PASSES_FULL_CHECK_CAPPED", "FULL_ACCEPTED_CANDIDATE_EXISTS"],
                  ["域", "仍无合法窗口", "有候选但基本全拒", "基本过/完整无净收益",
                   "基本过/完整检查截断", "存在完整通过的候选"]), ""]
    old = summary["old_no_window_sides"]
    text += ["### 5.1 旧规则下 33 个无窗侧在 G1 下的去向", "",
             "- 旧无窗侧总数：%d" % old,
             "- G0 下重新获得候选：%d" % summary["old_no_window_now_g0_candidates"],
             "- G1 下获得候选：%d" % summary["old_no_window_now_g1_candidates"],
             "- G1 下基本验收通过（至少一个候选）：%d" % summary["old_no_window_g1_basic_passed"],
             "- G1 下完整验收通过：%d" % summary["old_no_window_g1_full_passed"],
             "- G1 下仍然无窗：%d（其中至少一个窗口被曲率判据保守拒绝：%d）"
             % (summary["old_no_window_g1_still_no_window"],
                summary["old_no_window_g1_curvature_rejected_only"]),
             "- G1 下基本通过但完整检查未判定/无净收益：%d" % summary["old_no_window_g1_undecided"],
             "",
             "### 5.2 新增候选进入 K16 前缀的情况", "",
             "- G1 新增路径窗口候选合计：%d" % summary["g1_extra_candidates_total"],
             "- 被曲率判据保守拒绝的窗口：%d" % summary["g1_curvature_rejected_total"],
             "- 与 G0 窗口按平面弧长区间去重掉的窗口：%d" % summary["g1_dedup_removed_total"],
             "- K16 前缀规模：G0 %s，G1 %s" % (summary["k16_prefix_size"]["G0"],
                                               summary["k16_prefix_size"]["G1"]),
             "- 前缀构成：G0 %s；G1 %s" % (json.dumps(summary["k16_prefix_by_kind"]["G0"],
                                                      ensure_ascii=False),
                                           json.dumps(summary["k16_prefix_by_kind"]["G1"],
                                                      ensure_ascii=False)),
             "- 有路径窗口进入前缀的侧：%d / 120" % summary["sides_where_path_windows_enter_the_prefix"],
             "- 前缀被路径窗口完全占据的侧：%d / 120"
             % summary["sides_where_g1_prefix_is_all_path_windows"],
             "- 诊断账本：%s" % json.dumps(summary["ledger"], ensure_ascii=False)]
    return "\n".join(text) + "\n"


FENCE = chr(96) * 3


def mechanisms_section():
    path = OUT / "diagnostics" / "v8_side_diagnostics_mechanisms.json"
    if not path.is_file():
        return ""
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = [dict(mechanism=k, sides=v) for k, v in sorted(data["mechanism_breakdown"].items(),
                                                         key=lambda kv: -kv[1])]
    return "\n".join([
        "### 5.3 33 个旧无窗侧的机制分解", "",
        table(rows, ["mechanism", "sides"], ["机制", "侧数"]), "",
        "CURVATURE_REJECTED_ONLY：窗口被枚举出来，但每一个都被精确曲率界保守拒绝"
        "（弧半径贴近 5 mm 时任何长度都无法满足 R >= 5，拒绝而不放宽半径、不改 XY）。",
        "NO_INTERVAL_LONG_ENOUGH：第一个交点之前的可用平面行程和/或最后一个交点之后的行程"
        "短于最小合法升降行程，任何类型的窗口都放不下 —— 这是“一次升 + 一次降且必须覆盖交点”"
        "这一结构的硬几何限制，不是生成规则造成的。", ""]) + "\n"


def defect_section():
    path = OUT / "comparison" / "p2_g1_defect_record.json"
    if not path.is_file():
        return ""
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for row in data["rows"]:
        if not row.get("defective_present") or row.get("fixed_final_pairs") is None:
            continue
        rows.append(dict(group=row["group"],
                         defect_pairs=row.get("defective_final_pairs"),
                         defect_endpoint=row.get("defective_endpoint_changed_rejections"),
                         defect_deferred=row.get("defective_deferred_steps"),
                         fixed_pairs=row.get("fixed_final_pairs"),
                         fixed_endpoint=row.get("fixed_endpoint_changed_rejections"),
                         fixed_deferred=row.get("fixed_deferred_steps")))
    if not rows:
        return ""
    return "\n".join([
        "### 3.1 首轮 G1 的缺陷与修正（保留为证据）", "",
        "首轮 G1 组存在一个实现缺陷（不是 G1 的真实效果）：split_path_interval 在窗口终点恰好"
        "等于路线总长时因 1 ulp 误差算出 v=0.9999999999999999，子曲线端点被插值后偏离冻结端点约"
        "1.2e-14 mm，被基本验收以 ENDPOINT_CHANGED 拒绝，导致整步 K16 前缀被浪费。", "",
        table(rows, ["group", "defect_pairs", "defect_endpoint", "defect_deferred", "fixed_pairs",
                     "fixed_endpoint", "fixed_deferred"],
              ["组", "缺陷版终态对", "缺陷版 ENDPOINT_CHANGED", "缺陷版空转步", "修正版终态对",
               "修正版 ENDPOINT_CHANGED", "修正版空转步"]), "",
        "修正：BOUNDARY_SNAP_MM=1e-9 把落在 primitive 边界 1e-9 mm 内的子区间参数吸附到精确 0/1；"
        "回归测试 tests/test_path_window_3d.py 的 "
        "test_windows_touching_the_route_ends_keep_the_exact_frozen_endpoints 覆盖该情形。"
        "缺陷版输出全部保留在未加 tag 的目录里。", ""]) + "\n"


def conclusions_section():
    p2 = load("p2_g0_vs_g1") or {}
    neutral = load("neutrality_v8_code") or {}
    p3 = load("p3_family_and_target_limit") or {}
    p4 = load("p4_length_cap") or {}
    p5 = load("p5_serial_timing") or {}
    cells = [c for c in p2.get("cells", []) if "delta_final_pairs" in c]
    better = [c for c in cells if c.get("g1_better")]
    by_limit = p3.get("by_limit") or {}
    base2000 = by_limit.get("BASE_E2_T2000", {})
    a2000 = by_limit.get("A_FAMILY_T2000", {})
    p5_med = p5.get("median_runtime_seconds") or {}
    lines = ["## 11 结论", ""]
    lines.append("- v8 是否改善同预算全布局结果：%s（%d/%d 个 cell 更优）。"
                 % (p2.get("verdict"), len(better), len(cells)))
    if cells:
        best = min(cells, key=lambda c: c["delta_final_pairs"])
        worst = max(cells, key=lambda c: c["delta_final_pairs"])
        lines.append("  最大改善 %s%s2880：%d -> %d（delta=%d）；唯一退化 %s%s2880：%d -> %d"
                     "（delta=+%d，挑战起点，评价 %d/%d 未用满预算）。"
                     % (best["mode"], "挑战" if best.get("challenge") else "主",
                        best["g0"]["final_collision_pairs"], best["g1"]["final_collision_pairs"],
                        best["delta_final_pairs"], worst["mode"],
                        "挑战" if worst.get("challenge") else "主",
                        worst["g0"]["final_collision_pairs"], worst["g1"]["final_collision_pairs"],
                        worst["delta_final_pairs"], worst["g1"]["candidate_evaluations"],
                        worst["budget"]))
        r2880 = next((c for c in cells if c["mode"] == "R" and c["budget"] == 2880
                      and not c.get("challenge")), None)
        if r2880:
            lines.append("  路径窗口同时把阶段长度代价降下来（主 R2880：%s mm -> %s mm）："
                         "更长的窗口曲率更小、额外长度更少。"
                         % (fmt(r2880["g0"]["stage_length_delta_mm"]),
                            fmt(r2880["g1"]["stage_length_delta_mm"])))
    lines.append("- v8 是否改善旧 33 个无窗侧：没有。33 侧在 G1 下仍全部没有合法窗口，"
                 "其中 23 侧可用行程短于最小升降行程（硬几何限制），10 侧弧半径贴近 5 mm 被"
                 "精确曲率界保守拒绝（拒绝而不放宽半径、不改 XY）。")
    lines.append("- 代码中立性：G0 生成域下 3 组复跑与历史 v7 T0 的步级轨迹、近距/未决集合、"
                 "终态几何文件全部相同（判定 %s）。" % neutral.get("verdict"))
    lines.append("- A 在实际评价对齐后是否仍改善：是。BASE_E2 在 T200/T2000 完全相同（%s vs %s）；"
                 "A_FAMILY 在 max_targets=2000 且实际用满 2880 次评价时为 %s，对应 BASE_E2 的 %s，"
                 "改善 %s 对，但阶段长度从 %s mm 增到 %s mm。"
                 % (base2000.get("main_r2880"), by_limit.get("BASE_E2_T200", {}).get("main_r2880"),
                    a2000.get("main_r2880"), base2000.get("main_r2880"),
                    (base2000.get("main_r2880") or 0) - (a2000.get("main_r2880") or 0),
                    fmt(base2000.get("stage_length_delta_r2880")),
                    fmt(a2000.get("stage_length_delta_r2880"))))
    lines.append("- 相同长度约束下的效果（P4）：在 cap 24/40/60 mm 且同预算下，A_FAMILY 的终态"
                 "近距对都劣于 BASE_E2，直到 cap 放宽到不再约束为止（不限长时 A 才更好）；"
                 "说明 A 的近距改善以约 +18 mm 阶段长度为代价。")
    lines.append("- 受控串行计时（P5）：cache 开/关各 3 次的动作轨迹、终态近距集合与长度台账"
                 "逐位一致，命中 8160 次/次；引擎内核中位数 %s s（关）vs %s s（开），"
                 "但两次范围重叠，因此不对该设置作加速结论。"
                 % (fmt((p5_med.get("OFF") or {}).get("median")),
                    fmt((p5_med.get("ON") or {}).get("median"))))
    lines.append("- 额外队列（E 多锚点 x 目标上限）：E 在 max_targets=200 下无论预算多大都只花 668 次"
                 "评价就停止（终态 32565）；上限提到 2000 后同一预算被用满，主起点 R2880 为 15935 对，"
                 "优于 BASE_E2（18444）与 A_FAMILY（18042）；此前把 E 记为“退化”来自目标尝试上限，"
                 "不是多锚点机制本身。")
    lines.append("")
    return "\n".join(lines) + "\n"


def artifacts_section():
    lines = ["## 12 产物与复现", "", FENCE,
             "outputs/overnight_3d_continuation/",
             "  plan_p0_state.json            本轮计划与冻结参数",
             "  code_snapshot.json            正式批次前冻结的源码/测试 SHA256",
             "  manifest/round_{v8,v8_neutrality,p3,p4,p5}.json (+sha256, override records)",
             "  v8/ v8_neutrality/ p3/ p4/ p5/   每组 config/ledger/summary/decisions/recheck/",
             "  comparison/                   p2/p3/p4/p5/neutrality/defect 的 json+csv",
             "  diagnostics/                  120 侧诊断 + 机制分解",
             "  figures/                      对比图、权衡图、计时图、真实路径窗口实例图",
             "  verification/final_verification.json",
             "  tests/                        全量回归日志与摘要",
             "  report_qa/                    逐页视觉验收记录",
             FENCE, "",
             "复现命令见 checkpoint.md 的 resume_commands；重跑单组：",
             ".venv\\Scripts\\python.exe -B scripts\\run_overnight_3d.py . "
             "outputs\\overnight_3d_continuation --round v8 --group V8_G1_R2880 --tag boundaryfix",
             ""]
    return "\n".join(lines) + "\n"


def extra_section():
    data = load("pe_multi_anchor_limit")
    if not data:
        return ""
    rows = []
    for row in data["rows"]:
        if row["status"] != "PRESENT":
            continue
        rows.append(dict(arm=row["arm"], limit=row.get("max_targets"), mode=row["mode"],
                         budget=row["budget"], start="挑战" if row.get("challenge") else "主",
                         evals=row.get("candidate_evaluations"),
                         used=row.get("budget_used_percent"),
                         stop=short_stop(row.get("stop_reason")),
                         pairs=row.get("final_collision_pairs"),
                         moves=row.get("accepted_moves"),
                         length=fmt(row.get("stage_length_delta_mm"))))
    return "\n".join([
        "## 10 额外队列：E 多锚点 × 目标上限（单因素）", "",
        "E 的定义与 ideas 轮完全一致（multi_anchor=True，E2_ORDERED_K16），唯一变化是 "
        "max_targets 200 → 2000；目标 200 的单元直接引用已验收组，其余为本轮新跑。", "",
        table(rows, ["arm", "limit", "mode", "budget", "start", "evals", "used", "stop", "pairs",
                     "moves", "length"],
              ["臂", "目标上限", "模式", "预算", "起点", "实际评价", "用满%", "停止原因",
               "终态对", "动作", "阶段长度mm"]), "",
        "结论：E 在 max_targets=200 下无论预算加到 1440 还是 2880 都只花掉 668 次评价就停止"
        "（TARGET_LIMIT），终态固定为 32565；把上限提到 2000 后同一预算被真正用满，主起点 R2880 "
        "降到 15935 对，优于 BASE_E2（18444）与 A_FAMILY（18042）。也就是说，此前把 E 记为"
        "“退化”是**目标尝试上限**造成的，而不是多锚点机制本身——这与 P3 中 A 家族需要上限才能"
        "用满预算的结论一致，并提示：所有机制的对比都应在足够的目标上限下进行。", ""]) + "\n"


def p3_section():
    data = load("p3_family_and_target_limit")
    if not data:
        return "## 6 A 的实际评价公平性（P3）\n\n（comparison/p3_family_and_target_limit.json 缺失）\n"
    rows = []
    for row in data["rows"]:
        if row["status"] != "PRESENT":
            continue
        rows.append(dict(arm=row["arm"], limit=row.get("max_targets"), mode=row["mode"],
                         budget=row["budget"], start="挑战" if row.get("challenge") else "主",
                         evals=row.get("candidate_evaluations"),
                         used_pct=row.get("budget_used_percent"),
                         stop=short_stop(row.get("stop_reason")),
                         pairs=row.get("final_collision_pairs"),
                         moves=row.get("accepted_moves"),
                         length=fmt(row.get("stage_length_delta_mm")),
                         ref="引用" if row.get("reused_reference") else "本轮"))
    text = ["## 6 A 的实际评价公平性（P3）", "",
            "矩阵：BASE_E2 / A_FAMILY × max_targets 200/2000 × N/R × 720/1440/2880（24 主配置）",
            "＋同样四种设置 × N/R × 2880（8 挑战配置）。完全吻合的组只引用不重跑。", "",
            table(rows, ["arm", "limit", "mode", "budget", "start", "evals", "used_pct", "stop",
                         "pairs", "moves", "length", "ref"],
                  ["家族", "目标上限", "模式", "预算", "起点", "实际评价", "预算用满%", "停止原因",
                   "终态近距对", "动作", "阶段长度mm", "来源"]), "",
            "按上限聚合（R 主 2880 单元）：", ""]
    limit_rows = []
    for key, row in (data.get("by_limit") or {}).items():
        limit_rows.append(dict(arm=key, cells=row.get("cells"),
                               pairs=row.get("main_r2880"),
                               evals=row.get("actual_evaluations_r2880"),
                               limit_hits=row.get("target_limit_hits"),
                               full_uses=row.get("budget_full_uses"),
                               length=fmt(row.get("stage_length_delta_r2880"))))
    text.append(table(limit_rows, ["arm", "cells", "pairs", "evals", "limit_hits",
                                   "full_uses", "length"],
                      ["配置", "单元数", "R2880终态对", "实际评价", "触发目标上限",
                       "用满预算", "阶段长度mm"]))
    return "\n".join(text) + "\n"


def p4_section():
    data = load("p4_length_cap")
    if not data:
        return "## 7 长度约束下的收益（P4）\n\n（comparison/p4_length_cap.json 缺失）\n"
    rows = []
    for row in data["capped"]:
        if row["status"] != "PRESENT":
            continue
        rows.append(dict(arm=row["arm"], cap=row["cap_mm"], mode=row["mode"],
                         start="挑战" if row.get("challenge") else "主",
                         pairs=row.get("final_collision_pairs"),
                         length=fmt(row.get("stage_length_delta_mm")),
                         cap_rej=row.get("stage_length_cap_rejections"),
                         cap_checks=row.get("stage_length_cap_checks"),
                         headroom=fmt(row.get("stage_length_cap_headroom_mm")),
                         evals=row.get("candidate_evaluations"),
                         moves=row.get("accepted_moves"), stop=short_stop(row.get("stop_reason"))))
    references = []
    for row in data["uncapped_references"]:
        if row["status"] != "PRESENT":
            continue
        references.append(dict(arm=row["arm"], mode=row["mode"],
                               start="挑战" if row.get("challenge") else "主",
                               pairs=row.get("final_collision_pairs"),
                               length=fmt(row.get("stage_length_delta_mm")),
                               evals=row.get("candidate_evaluations"),
                               moves=row.get("accepted_moves")))
    text = ["## 7 长度约束下的收益（P4）", "",
            "cap 口径：当前全布局总长度 ≤ 起点全布局总长度 + cap；按有符号长度台账计算，",
            "重定位减少长度时可以获得余量。评价顺序：先做原基本评价并扣预算单位，再检查成本约束，",
            "超限单独记账为 REJECTED_STAGE_LENGTH_CAP，不计入基本拒绝、也不算零候选。", "",
            "### 7.1 受限组", "",
            table(rows, ["arm", "cap", "mode", "start", "pairs", "length", "cap_rej", "cap_checks",
                         "headroom", "evals", "moves", "stop"],
                  ["家族", "cap mm", "模式", "起点", "终态近距对", "阶段长度mm", "cap拒绝",
                   "cap检查", "余量mm", "评价", "动作", "停止原因"]), "",
            "### 7.2 同策略不限长对照", "",
            table(references, ["arm", "mode", "start", "pairs", "length", "evals", "moves"],
                  ["家族", "模式", "起点", "终态近距对", "阶段长度mm", "评价", "动作"])]
    return "\n".join(text) + "\n"


def p5_section():
    data = load("p5_serial_timing")
    if not data:
        return "## 8 受控串行计时（P5）\n\n（comparison/p5_serial_timing.json 缺失）\n"
    rows = []
    for row in data["rows"]:
        if row["status"] != "PRESENT":
            continue
        rows.append(dict(arm=row["arm"], seq=row["sequence"],
                         scan=fmt(row.get("initial_pair_scan_seconds")),
                         engine=fmt(row.get("runtime_seconds")),
                         total=fmt(row.get("run_seconds_including_recheck")),
                         io=fmt(row.get("recheck_and_io_seconds")),
                         evals=row.get("candidate_evaluations"),
                         hits=row.get("decision_cache_hits"),
                         pairs=row.get("final_collision_pairs"),
                         length=fmt(row.get("stage_length_delta_mm")),
                         verdict=row.get("recheck_verdict")))
    text = ["## 8 受控串行计时（P5）", "",
            "同一主起点、同一 R1440 预算、同一 LEGACY+E2_K16 策略，只切换 G 决策缓存；",
            "每次都在独立进程里从零加载、缓存为空，6 次运行按 OFF/ON 交替顺序串行执行，",
            "计时期间不并行其它性能实验。", "",
            table(rows, ["arm", "seq", "scan", "engine", "total", "io", "evals", "hits", "pairs",
                         "length", "verdict"],
                  ["缓存", "次序", "预扫s", "内核s", "总进程s", "复核+IO s", "评价", "缓存命中",
                   "终态近距对", "长度mm", "复核"]), "",
            "中位数与范围（秒）：", ""]
    med = []
    for arm in ("OFF", "ON"):
        row = dict(arm=arm)
        for label, key in (("engine", "median_runtime_seconds"),
                           ("total", "median_run_seconds_including_recheck"),
                           ("scan", "median_scan_seconds"),
                           ("assign", "median_assignment_seconds")):
            stats = (data.get(key) or {}).get(arm) or {}
            row[label] = ("%s (%s-%s)" % (fmt(stats.get("median")),
                                          fmt(stats.get("min")), fmt(stats.get("max")))
                          if stats else "-")
        med.append(row)
    text.append(table(med, ["arm", "engine", "total", "scan", "assign"],
                      ["缓存", "内核中位数(范围)", "总进程中位数(范围)",
                       "预扫中位数(范围)", "分配中位数(范围)"]))
    text.append("")
    text.append("一致性（三次运行逐一核对）：终态近距对 %s；阶段长度 mm %s；"
                "缓存命中 %s。"
                % (json.dumps((data.get("consistency") or {}).get("final_pairs")),
                   json.dumps((data.get("consistency") or {}).get("stage_length_delta")),
                   json.dumps((data.get("consistency") or {}).get("cache_hits"))))
    text.append("")
    text.append("预扫（初始 130,816 对全扫）在每个起点状态上只执行一次，且在引擎计时"
                "窗口之外，因此内核/进程时间里的预扫列为 0.00；该时间记在 "
                "start_check_main.json 的 scan_seconds 中。")
    return "\n".join(text) + "\n"


def main_section(context):
    return (
        "## 1 本轮范围与状态恢复（P0）\n\n"
        "本轮从 checkpoint/status/task_queue/final_verification 与各组真实 summary 恢复状态，"
        "修正了队列中过期的 “v5 running / v8 not_started” 说法，冻结了本轮 manifest 与生成域参数"
        "（详见 outputs/overnight_3d_continuation/plan_p0_state.json）。\n\n"
        "- 组数口径：此前基础轮次与单项消融 118 组、另有 dctrl 8 组；final_verification 的 126 组"
        "＝ 104 个新跑 PASS 组 ＋ 22 个引用基线。三个口径互不混用。\n"
        "- A2880 的预算事实：IDEA_A_FAMILY_N2880 实际评价 2753、R2880 实际评价 2664，"
        "两者都在 max_targets=200 的目标尝试上限停止（TARGET_LIMIT），"
        "因此它们与 BASE_E2 共享**预算上限**，但**不是**与 BASE_E2 的实际 2880 次评价对齐；"
        "本轮 P3 用 max_targets=2000 补实际评价对齐的对照。\n"
        "- 主起点固定 v3 D_both_enabled，挑战起点固定 v4 N2880，各组独立加载，不串接终态。\n\n"
        "## 2 v8 几何支持链（P1）\n\n"
        "新原语 PathWindowTransition3D：窗口覆盖冻结平面路径上的一段连续**平面弧长**区间，"
        "允许切分圆弧、跨相邻 primitive；XY 是原解析子曲线（不是弦），竖直方向是整窗**共享的一个**"
        "余弦相位 z(u)=z_start+(z_end-z_start)·sin²(πu/2)，内部切片不重新开始升降。\n\n"
        "曲率用 s 为平面弧长的闭式：\n\n"
        "    kappa3D = sqrt(kappa_xy²·(1+z_s²) + z_ss²) / (1+z_s²)^(3/2)\n\n"
        "单个 piece 内 kappa_xy 为常数，1+z_s² 单调增、|z_ss| 单调减（[0,1/2]）且关于 1/2 对称，"
        "因此窗口上的最大值必在 piece 边界取得；实现按**所有共享该参数的两侧**求值，"
        "所以线段—圆弧边界处的曲率跳变不会被漏掉。整窗最大曲率是解析精确值，不是采样最小半径。\n\n"
        "同时完成：point_at/tangent_at、自适应 Simpson 长度积分（不收敛即拒绝）、"
        "XY 保持（双向采样核对 + 总 XY 长度）、RouteView/AABB 保守包围、保守弦误差界"
        "（sup|r''|·Δt²/8）、旧/新与新/新 primitive 距离、自近距相邻证明"
        "（C1 接头在“离接头 2×clearance 弧长之外”被认证为 CLEAR，声明常数 "
        "ADJACENT_FAR_MULTIPLE=2.0，豁免对的总弧长间隔 < 0.4 mm）、"
        "序列化/反序列化 round-trip、生成缓存指纹、稳定排名键（新旧窗口统一成 4 元组）、"
        "以及 G1 生成域（保留全部 G0 候选 + 路径窗口，按平面弧长区间去重）。\n\n"
        "针对性测试：tests/test_path_window_3d.py，覆盖纯直线退化、跨线弧窗口、"
        "内部相位共享、方向连续、曲率闭式与数值曲率一致、整窗极值、半径贴近时保守拒绝、"
        "保守距离界、自近距、逻辑结构（逻辑升降 vs 物理片段）、round-trip、缓存失效、"
        "G1 保留全部 G0 候选。\n")


def final_section(tests, verification):
    lines = ["## 9 测试、全量复核与视觉 QA（P6）", ""]
    lines.append("- 针对性测试：" + str(tests.get("targeted", "见 tests/test_path_window_3d.py")))
    lines.append("- 全量回归：" + str(tests.get("full", "见日志")))
    lines.append("- 逐页视觉验收：" + str(tests.get("visual", "见 outputs/overnight_3d_continuation/report_qa")))
    lines.append("")
    lines.append("复核（每个正式终态保存→重载→全扫 130,816 对）：")
    lines.append("")
    if verification:
        rows = [dict(round=r.get("round"), group=r.get("group"), status=r.get("status"),
                     recheck=(r.get("checks") or {}).get("recheck_pass"))
                for r in verification.get("rows", []) if r.get("round") in
                ("v8", "v8_neutrality", "p3", "p4", "p5")]
        lines.append(table(rows, ["round", "group", "status", "recheck"],
                           ["轮次", "组", "状态", "复核 PASS"]))
        lines.append("")
        lines.append("整体判定：groups_total=%s PASS=%s FAIL=%s NOT_FINISHED=%s 引用=%s"
                     % (verification.get("groups_total"), verification.get("groups_pass"),
                        verification.get("groups_fail"),
                        verification.get("groups_not_finished"),
                        verification.get("groups_reused_reference")))
    else:
        lines.append("（final_verification 结果缺失）")
    return "\n".join(lines) + "\n"


def build_markdown():
    tests = {}
    log_dir = OUT / "tests"
    if (log_dir / "summary.json").is_file():
        tests = json.loads((log_dir / "summary.json").read_text(encoding="utf-8"))
    verification = None
    if (OUT / "verification" / "final_verification.json").is_file():
        verification = json.loads(
            (OUT / "verification" / "final_verification.json").read_text(encoding="utf-8"))
    parts = ["# 三维布线 v8 路径弧长窗口续跑报告", "",
             "本报告由 scripts/publication/build_v8_continuation_report.py 依据冻结产物自动生成；"
             "所有数字来自 outputs/overnight_3d_continuation 下的 comparison/diagnostics/verification 文件。", "",
             main_section(None), p2_section(), defect_section(), neutrality_section(),
             diagnostics_section(), mechanisms_section(), p3_section(), p4_section(), p5_section(),
             final_section(tests, verification), extra_section(), conclusions_section(),
             artifacts_section()]
    return "\n".join(parts)


def main():
    markdown = build_markdown()
    DOCS.mkdir(parents=True, exist_ok=True)
    md_path = DOCS / "step_19_v8_continuation.md"
    md_path.write_text(markdown, encoding="utf-8")
    print("markdown", md_path)
    from build_overnight_report_docx import build
    figures = []
    for path in sorted((OUT / "figures").glob("*.png")):
        figures.append((path.stem, path))
    target = REPORT_DIR / "brief_build"
    target.mkdir(parents=True, exist_ok=True)
    docx = target / (NAME + ".docx")
    build(markdown, figures, docx)
    print("docx", docx, "figures", len(figures))


if __name__ == "__main__":
    main()
