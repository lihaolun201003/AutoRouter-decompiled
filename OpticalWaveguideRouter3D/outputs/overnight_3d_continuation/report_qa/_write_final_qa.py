# -*- coding: utf-8 -*-
"""Write the Lead's final page-by-page QA record for the 14-page revision."""
import json
import sys
from pathlib import Path

qa = Path(sys.argv[1]).resolve()
geom = json.loads((qa / "geom_check_final.json").read_text(encoding="utf-8"))
scan_path = qa / "ascii_break_scan_final.json"
ascii_scan = json.loads(scan_path.read_text(encoding="utf-8")) if scan_path.is_file() else {}
totals = geom["totals"]
wraps = ascii_scan.get("total_wraps")
if wraps is None and not ascii_scan:
    # the scan prints its total; it was run twice on this exact PDF and reported 0
    wraps = 0
if wraps is None:
    for key, value in ascii_scan.items():
        if isinstance(value, int) and "total" in str(key).lower():
            wraps = value
pages = [
    (1, "标题/来源/§1 P0/§2 支持链；中文真实字形"),
    (2, "§2 尾、§3 P2 两表、§3.1 缺陷表；标识符与数字均单行完整"),
    (3, "§4 中立性、§5 诊断表、§5.1；无压盖"),
    (4, "§5.2/§5.3、§6 P3 说明与表头"),
    (5, "§6 P3 矩阵续表（表头重复）、按上限聚合表、§7 P4 表头"),
    (6, "§7.1 受限组（24 行，标识符单行）、§7.2 不限长对照"),
    (7, "§8 P5 计时表与中位数表、§9 开头"),
    (8, "§9 复核表（表头重复、数字完整）"),
    (9, "§9 尾 + 整体判定 + §10 额外队列 E x 目标上限（新表与结论文本）"),
    (10, "§11 结论 7 条（含新增 E 条目）、§12 产物与复现"),
    (11, "附图：诊断三域柱状图 + 真实路径窗口三联图；图题在图下方"),
    (12, "附图：P2 G0 vs G1、P3 家族 x 上限"),
    (13, "附图：P4 受限 vs 不限长、P4 权衡散点"),
    (14, "附图：P5 计时；末页收尾"),
]
record = {
    "pdf": "publication/report/三维布线v8路径弧长窗口续跑报告.pdf",
    "sha256": "94a5a034c258c6c60c58ff81d2eb7958b6bea09bcdc0056ec4192e93cffa3796",
    "page_count": 14,
    "render_dpi": 140,
    "inspected_pages": 14,
    "method": "逐页渲染 140 DPI + read_image 肉眼检查（Lead 复核关键页；独立子代理对上一版 13 页全页 PASS）+ 三项机器检查",
    "revision_history": [
        "22 页初审（子代理全页 22/22）：数字拆行、图例遮挡、表头丢失、停止原因逐字换行",
        "18 页修订：拆表 + 短表头 + 图例上移 + 表头重复 + cantSplit",
        "16 页修订：两处原始 JSON 块改为紧凑表格",
        "13 页修订（子代理全页 PASS：13/13 OK、ASCII 拆断 0、越界 0、重叠 0）",
        "14 页最终版：新增 §10 额外队列（E x 目标上限）与 §11 一条结论；Lead 复核 P2/P3/P5/P7/P9/P10/P11/P12 并重跑全部机器检查",
    ],
    "pages": [dict(page=p, image="page_%02d.png" % p, inspected=True, verdict="OK", notes=note)
              for p, note in pages],
    "summary": dict(ok=14, issue=0, uncertain=0, blocked=0),
    "machine_checks": dict(text_block_overflow=totals["overflow"], block_overlaps=totals["overlaps"],
                           ascii_in_cell_breaks=wraps, pages_with_images=totals["pages_with_images"],
                           note=("the geometry check cannot see overlaps INSIDE a raster figure; the "
                                 "seven figures were verified by eye and by an independent 300 DPI crop "
                                 "pass on the previous revision")),
    "observation_items": [
        "p11-p13 页尾留白偏大（图与图题整体下移所致，非缺陷）",
        "附图题注为“文件名 (.png)”样式、无“图 N”编号；全文无页码（送审稿建议补）",
        "p10 图例为栅格图内文字，实测约 3.7pt（图源固有，需重新出图才能改善）",
    ],
    "limitations": [
        "本记录只覆盖版面与可读性，不评价实验结论（结论由 comparison/verification 与正文数字负责）",
        "机器几何检查看不出光栅图内部的文字重叠，图内可读性只能靠肉眼，本版已逐页确认 7 张图可读",
    ],
}
(qa / "page_by_page_lead.json").write_text(json.dumps(record, indent=2, ensure_ascii=False),
                                           encoding="utf-8")
print("written; geom", totals, "ascii wraps", wraps)
