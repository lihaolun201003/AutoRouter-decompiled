# -*- coding: utf-8 -*-
import json, sys, os, shutil, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
out = sys.argv[1]
pages_dir = os.path.join(out, "pages")
pdf_path = sys.argv[2]
dpi = int(sys.argv[3])

# 1) move page PNGs to the top level of the QA dir (spec: page_01.png ... in that directory)
moved = []
for n in range(1, 33):
    name = "page_%02d.png" % n
    src = os.path.join(pages_dir, name)
    dst = os.path.join(out, name)
    if os.path.exists(src):
        shutil.move(src, dst); moved.append(name)
if os.path.isdir(pages_dir) and not os.listdir(pages_dir):
    os.rmdir(pages_dir)

# 2) load inputs
meta = {p["page"]: p for p in json.load(open(os.path.join(out, "_page_meta.json"), encoding="utf-8"))}
geo  = {p["page"]: p for p in json.load(open(os.path.join(out, "_geometry_raw.json"), encoding="utf-8"))["pages"]}
geothr = json.load(open(os.path.join(out, "_geometry_raw.json"), encoding="utf-8"))["thresholds"]
imgrows = json.load(open(os.path.join(out, "_image_info.json"), encoding="utf-8"))
imgby = {}
for r in imgrows:
    imgby.setdefault(r["page"], []).append(r)

global_issues = [
 {"id":"G1","title":"段落内硬换行残留","severity":"中","detail":"源 Markdown 的段内软换行被逐行保留为硬换行，导致句子在中间被拆行、下一行另行起排并带缩进、行距忽大忽小。第 1 页起即出现，第 1-15 页普遍存在。","evidence":["page_01.png","page_03.png","page_05.png","page_06.png"]},
 {"id":"G2","title":"内联代码字面反引号残留","severity":"低","detail":"所有 \u0060code\u0060 内联代码的反引号被原样印出（如 \u0060src/overnight_engine_3d.py\u0060），未转换为等宽代码样式。第 12 页 5.3 节最密集。","evidence":["page_01.png","page_12.png","page_13.png"]},
 {"id":"G3","title":"表格无『表 X』题注、图无『图 X』编号","severity":"低","detail":"全文 11 张 Word 表均无表题；32 幅图有图题（均在图下方居中）但无编号。源 Markdown 中同样不存在题注行，属既定风格而非转换丢失。","evidence":["page_02.png","page_16.png"]},
 {"id":"G4","title":"图内文字实际印刷字号普遍偏小","severity":"低-中","detail":"32 幅图源图宽度统一为 1219px、统一排版为 439.2pt 宽（有效约 200 DPI，分辨率达标）；但图内坐标刻度、图例、尤其『数据来源』脚注相对画布很小，折算印刷字号约 2.5-5pt，低于常规可读下限（约 6pt）。属缩放/出图设置问题，非分辨率不足。","evidence":["page_16.png","page_17.png","page_21.png","page_30.png"]}
]

page_issues = [
 {"page":1,"severity":"中","title":"表头孤行 + 跨页表头未重复","detail":"页尾仅有表头行，其 6 行数据全部落到第 2 页且第 2 页未重复表头。","evidence":["page_01.png","_zoom_p1_bottomtable.png","page_02.png","_zoom_p2_toptable.png"]},
 {"page":2,"severity":"中","title":"跨页表格无表头（承接第1页同一表格）","detail":"页首 6 行 V5_LEGACY_* 数据无表头。","evidence":["page_02.png","_zoom_p2_toptable.png"]},
 {"page":5,"severity":"中","title":"Markdown 标题标记泄漏到正文","detail":"正文出现字面『### 2.3 关键结论』，## 未被转换，导致该标题既未成标题又粘在上一段句尾。","evidence":["page_05.png","_zoom_p5_heading2.png"]},
 {"page":8,"severity":"中","title":"表格行在页底被截断","detail":"4.1 表末行只印出『2,664 / 达』，余下文字落到第 9 页。","evidence":["page_08.png","page_09.png"]},
 {"page":9,"severity":"中","title":"页首出现表格残行（承接第8页）","detail":"残行 6 格为空、仅末列『目标上限』，且无表头。","evidence":["page_09.png"]},
 {"page":20,"severity":"中","title":"group_table 图内字号约 3.2pt，不可读","detail":"v5_f8_group_table 为 15 行×14 列宽表截图，缩放到 439×126pt。","evidence":["page_20.png","_zoom_p20_grouptable.png"]},
 {"page":24,"severity":"中","title":"group_table 不可读 + 末图图题被推到下一页","detail":"v6_f8_group_table 约 3.2pt；v7_f1 图题跨页到第 25 页页首。","evidence":["page_24.png","_zoom_p24_grouptable.png","_zoom_p24_bottom.png"]},
 {"page":25,"severity":"中","title":"页首孤立图题，且紧邻的是另一幅图","detail":"第 24 页末图 v7_f1 的图题出现在第 25 页页首，其正下方是 v7_f2，极易误配。","evidence":["_zoom_p25_top.png","page_25.png"]},
 {"page":28,"severity":"中","title":"group_table 不可读 + 末图图题跨页 + 图例遮挡数据","detail":"v7_f8_group_table 约 3pt；ideas_f1 图题跨到第 29 页；ideas_f1 (a) 子图 18 项图例压住曲线末端。","evidence":["page_28.png"]},
 {"page":29,"severity":"中-高","title":"页首孤立图题 + ideas_f2 被压成 58pt 高窄条","detail":"ideas_f2_same_budget_N_vs_R 源图 1219×161px，多面板压成一条，图内文字完全不可读。","evidence":["page_29.png"]},
 {"page":30,"severity":"中-高","title":"x 轴刻度标签严重重叠成灰色不可读块","detail":"分组数过多导致数十个 IDEAS.* 标签互相叠印。","evidence":["page_30.png","_zoom_p30_ticks.png"]},
 {"page":31,"severity":"中-高","title":"刻度标签重叠 + 数值标注互相重叠并覆盖柱体","detail":"ideas_f5 (a) 子图低值柱区标注叠印。","evidence":["page_31.png","_zoom_p31_boxes.png"]},
 {"page":32,"severity":"中","title":"刻度标签重叠 + group_table 约 2.5pt 不可读","detail":"另 (c) 子图柱顶与坐标区上边界齐平，观感似截断（放大核对后确认数据未被裁切，仅无留白）。","evidence":["page_32.png","_zoom_p32_panelb.png"]}
]

pages_out = []
for n in range(1, 33):
    m = meta[n]; g = geo[n]
    imgs = imgby.get(n, [])
    pages_out.append({
        "page": n,
        "image": "page_%02d.png" % n,
        "inspected": True,
        "inspection_method": "read_image on the 140 DPI page render; targeted PyMuPDF high-zoom crops for flagged regions",
        "findings": m["findings"],
        "verdict": m["verdict"],
        "notes": m["notes"],
        "global_issues_apply": m.get("global_issues_apply", False),
        "figures_on_page": [
            {"src_px": [i["px"][0], i["px"][1]], "placed_pt": i["placed_pt"], "effective_dpi": i["eff_dpi"][0]}
            for i in imgs
        ],
        "geometry_check": {
            "note": "机器检查，与上面的视觉结论相互独立；不要与本页 findings 混为一谈。",
            "page_size_pt": g["page_size_pt"],
            "text_or_image_block_count": g["block_count"],
            "out_of_bleed_count": g["out_of_bleed_count"],
            "out_of_bleed": g["out_of_bleed"],
            "out_of_margin_count": g["out_of_margin_count"],
            "out_of_margin_sample": g["out_of_margin_sample"],
            "overlap_count": g["overlap_count"],
            "overlaps": g["overlaps"]
        }
    })

overlap_pages = [p["page"] for p in pages_out if p["geometry_check"]["overlap_count"] > 0]
ok = [p["page"] for p in pages_out if p["verdict"] == "OK"]
issue = [p["page"] for p in pages_out if p["verdict"] == "ISSUE"]
unc = [p["page"] for p in pages_out if p["verdict"] == "UNCERTAIN"]
blk = [p["page"] for p in pages_out if p["verdict"] == "BLOCKED"]

result = {
 "pdf": pdf_path,
 "page_count": 32,
 "render_dpi": dpi,
 "render_engine": "PyMuPDF 1.28.2 (fitz) via project venv python 3.10.11",
 "qa_dir": out,
 "inspected_page_count": 32,
 "pages": pages_out,
 "summary": {
   "visual": {
     "inspected": 32,
     "OK": len(ok), "ISSUE": len(issue), "UNCERTAIN": len(unc), "BLOCKED": len(blk),
     "OK_pages": ok, "ISSUE_pages": issue, "UNCERTAIN_pages": unc,
     "verdict_convention": "verdict 只针对本页特有的缺陷。仅带全局性问题(G1-G4)的页面仍判 OK，但会把全局问题写入该页 findings 并置 global_issues_apply=true。",
     "chinese_glyphs": "32 页全部为真实中文字形，未发现方框/豆腐块/乱码/缺字",
     "clipping": "32 页均未发现文字或图片被页边裁切、未发现文字互相重叠（正文与表格层面）、未发现空白页",
     "captions": "32 幅图各有且仅有一个图题（共 32 个图题），图题均居中且位于图下方；例外：第 24→25 页与第 28→29 页各有 1 个图题被分页推到下一页页首，与自己的图分离",
     "table_captions": "11 张 Word 表均无表题（源文件亦无），此项为 N/A"
   },
   "global_issues": global_issues,
   "page_specific_issues": page_issues,
   "geometry_check_summary": {
     "thresholds": geothr,
     "pages_with_out_of_bleed": [p["page"] for p in pages_out if p["geometry_check"]["out_of_bleed_count"] > 0],
     "pages_with_out_of_margin": [p["page"] for p in pages_out if p["geometry_check"]["out_of_margin_count"] > 0],
     "pages_with_overlap_flag": overlap_pages,
     "total_overlap_flags": sum(p["geometry_check"]["overlap_count"] for p in pages_out),
     "assessment": "越界检查：32 页全部 0 处超出可打印范围(18pt 血边区)与 0 处超出 54pt 常规页边距。重叠检查：第 2/3/5/7/8/10/11/15 页共报出 40 处文本块 bbox 重叠，人工逐页核对这 8 页后确认均为 PyMuPDF 对 Word 表格的抽取伪影——同一行的多个单元格文本被合并成一个横跨整行的块，与同时输出的按单元格块 bbox 相交；页面实际渲染中不存在文字互相压盖。故这些重叠标记不构成视觉缺陷。注意该机器检查只能发现文本层与位图外框的重叠，无法发现光栅图内部的文字重叠（第 30/31/32 页的图内标签重叠正是由人工视觉检查发现，而非本项机器检查）。"
   },
   "limitations": [
     "本轮对全部 32 页做了 140 DPI 整页视觉检查，并对 12 处可疑区域做了 3-9 倍放大复核（_zoom_*.png）。",
     "未对全部 32 幅图的每一个图内数据标注做逐一放大核对；对未放大核对的图，仅确认了其整体完整性、是否被裁切与图题位置。",
     "机器几何检查基于文本块与位图外框，不能检出光栅图内部的元素重叠、遮挡或字号过小。",
     "本轮不修改任何 PDF/DOCX/源码，仅新增 QA 产物。"
   ]
 }
}
with open(os.path.join(out, "page_by_page.json"), "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=1)
print("OK moved=%d pages=%d issue=%d ok=%d unc=%d" % (len(moved), len(pages_out), len(issue), len(ok), len(unc)))
