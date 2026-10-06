# -*- coding: utf-8 -*-
"""Machine geometry check (v2) for the v8 continuation report PDF.

Two independent tests:
  A) block level  : PyMuPDF get_text('blocks') bbox out-of-page and block/block overlap
  B) line level   : get_text('dict') line bboxes - real ink-collision test (a line of text
                    sitting on top of another line), plus line out-of-page.
LIMITATION (recorded in the output): neither test can see text that overlaps inside an
embedded raster figure; that is covered by the page-by-page visual inspection only.
"""
import json, sys, os
import fitz

sys.stdout.reconfigure(encoding="utf-8")
PDF = r"C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D\publication\report\三维布线v8路径弧长窗口续跑报告.pdf"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "geom_check.json")


def inter(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0, None
    return (x1 - x0) * (y1 - y0), (x0, y0, x1, y1)


doc = fitz.open(PDF)
res = {
    "pdf": PDF, "pages": doc.page_count,
    "method": "PyMuPDF: (A) get_text('blocks') block bboxes; (B) get_text('dict') line bboxes; get_image_info",
    "limitation": "无法检测光栅图内部文字重叠/截断（图内像素不属于文字层）；图内可读性只能靠逐页视觉检查（本项目另做了 300 DPI 图区裁剪目检）。",
    "page_checks": [],
}
tot_block_ov = tot_line_ov = tot_overflow = 0
for i, page in enumerate(doc):
    pr = page.rect
    W, H = pr.width, pr.height
    blocks = [b for b in page.get_text("blocks") if b[6] == 0 and b[4].strip()]
    d = page.get_text("dict")
    lines = []
    for blk in d["blocks"]:
        if blk.get("type") != 0:
            continue
        for ln in blk["lines"]:
            txt = "".join(s["text"] for s in ln["spans"]).strip()
            if txt:
                lines.append({"bbox": tuple(ln["bbox"]), "text": txt})
    imgs = page.get_image_info()

    overflow = []
    for b in blocks:
        bb = tuple(round(v, 2) for v in b[:4])
        if bb[0] < -0.5 or bb[1] < -0.5 or bb[2] > W + 0.5 or bb[3] > H + 0.5:
            overflow.append({"bbox": bb, "text": b[4].strip()[:60]})
    line_overflow = []
    for ln in lines:
        bb = tuple(round(v, 2) for v in ln["bbox"])
        if bb[0] < -0.5 or bb[1] < -0.5 or bb[2] > W + 0.5 or bb[3] > H + 0.5:
            line_overflow.append({"bbox": bb, "text": ln["text"][:60]})

    overlaps = []
    for a in range(len(blocks)):
        for c in range(a + 1, len(blocks)):
            area, rect = inter(blocks[a][:4], blocks[c][:4])
            if area <= 1.0:
                continue
            sa = (blocks[a][2] - blocks[a][0]) * (blocks[a][3] - blocks[a][1])
            sb = (blocks[c][2] - blocks[c][0]) * (blocks[c][3] - blocks[c][1])
            frac = area / max(1e-6, min(sa, sb))
            if frac >= 0.12 and area >= 12.0:
                overlaps.append({"a": blocks[a][4].strip()[:50], "b": blocks[c][4].strip()[:50],
                                 "area_pt2": round(area, 1), "frac_of_smaller": round(frac, 3)})

    line_overlaps = []
    for a in range(len(lines)):
        for c in range(a + 1, len(lines)):
            area, rect = inter(lines[a]["bbox"], lines[c]["bbox"])
            if area <= 2.0:
                continue
            line_overlaps.append({"a": lines[a]["text"][:50], "b": lines[c]["text"][:50],
                                  "area_pt2": round(area, 1), "rect": [round(v, 1) for v in rect]})

    img_rects = [[round(v, 1) for v in im["bbox"]] for im in imgs]
    img_text_overlap = []
    for im in imgs:
        for ln in lines:
            area, rect = inter(im["bbox"], ln["bbox"])
            if area > 4.0:
                img_text_overlap.append({"image_bbox": [round(v, 1) for v in im["bbox"]],
                                         "text": ln["text"][:50], "area_pt2": round(area, 1)})
    ys = [b[1] for b in blocks] + [b[3] for b in blocks] + [im["bbox"][1] for im in imgs] + [im["bbox"][3] for im in imgs]
    xs = [b[0] for b in blocks] + [b[2] for b in blocks] + [im["bbox"][0] for im in imgs] + [im["bbox"][2] for im in imgs]
    content = None
    if ys:
        content = {"x0": round(min(xs), 1), "y0": round(min(ys), 1), "x1": round(max(xs), 1), "y1": round(max(ys), 1),
                   "bottom_gap_pt": round(H - max(ys), 1), "bottom_gap_cm": round((H - max(ys)) / 72 * 2.54, 2),
                   "bottom_gap_pct_of_page": round((H - max(ys)) / H * 100, 1)}
    tot_block_ov += len(overlaps); tot_line_ov += len(line_overlaps); tot_overflow += len(overflow) + len(line_overflow)
    res["page_checks"].append({
        "page": i + 1, "page_size_pt": [round(W, 1), round(H, 1)],
        "text_blocks": len(blocks), "text_lines": len(lines), "images": len(imgs), "image_rects": img_rects,
        "image_assets": sorted({str(im["width"]) + "x" + str(im["height"]) for im in imgs}),
        "chars": sum(len(b[4].strip()) for b in blocks),
        "overflow_blocks": overflow, "overflow_lines": line_overflow,
        "block_overlap_pairs": overlaps, "line_overlap_pairs": line_overlaps,
        "image_text_overlaps": img_text_overlap, "content_bbox": content,
    })
doc.close()
res["totals"] = {"overflow_blocks_and_lines": tot_overflow, "block_overlap_pairs": tot_block_ov,
                 "line_overlap_pairs": tot_line_ov,
                 "interpretation": "block 级重叠经逐页目检全部为相邻表格行/表头单元格的包围盒行距artifact；line 级重叠才是真实墨迹压字。"}
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(res, f, ensure_ascii=False, indent=1)

print("pages:", res["pages"])
for p in res["page_checks"]:
    print("p%02d blocks=%d lines=%d chars=%d imgs=%d overflow=%d/%d blockOv=%d lineOv=%d bottom_gap=%.1fpt(%.2fcm,%.1f%%)" % (
        p["page"], p["text_blocks"], p["text_lines"], p["chars"], p["images"],
        len(p["overflow_blocks"]), len(p["overflow_lines"]),
        len(p["block_overlap_pairs"]), len(p["line_overlap_pairs"]),
        p["content_bbox"]["bottom_gap_pt"], p["content_bbox"]["bottom_gap_cm"], p["content_bbox"]["bottom_gap_pct_of_page"]))
print("TOTALS", json.dumps(res["totals"], ensure_ascii=False)[:200])
