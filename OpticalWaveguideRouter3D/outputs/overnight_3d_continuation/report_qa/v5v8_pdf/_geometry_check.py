# -*- coding: utf-8 -*-
"""Machine geometry check: text/image block bboxes vs printable area, and pairwise overlaps.
Read-only on the source PDF. Does NOT replace visual inspection."""
import sys, json
import fitz

pdf_path = sys.argv[1]
doc = fitz.open(pdf_path)

# A4/Letter printable margin heuristic: 0.25in = 18pt hard bleed boundary.
BLEED = 18.0
# "Content area" heuristic used by most Word Chinese report templates.
MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B = 54.0, 54.0, 54.0, 54.0
OVERLAP_MIN = 40.0   # pt^2 of intersection before we call it a real overlap
OVERLAP_RATIO = 0.35 # and >=35% of the smaller block area

pages_out = []
for i in range(doc.page_count):
    page = doc[i]
    pr = page.rect
    blocks = []
    for b in page.get_text("blocks"):
        x0, y0, x1, y1, txt, bno, btype = b[0], b[1], b[2], b[3], b[4], b[5], b[6]
        txt_s = (txt or "").strip()
        if not txt_s:
            continue
        blocks.append({"type": "text" if btype == 0 else "image", "bbox": [round(x0,2), round(y0,2), round(x1,2), round(y1,2)],
                       "preview": txt_s[:60].replace("\n", " ")})
    for im in page.get_image_info():
        bb = im.get("bbox")
        if bb:
            blocks.append({"type": "image_pix", "bbox": [round(v,2) for v in bb], "preview": "image %sx%s" % (im.get("width"), im.get("height"))})

    out_of_bleed = []
    out_of_margin = []
    for bl in blocks:
        x0, y0, x1, y1 = bl["bbox"]
        if x0 < BLEED or y0 < BLEED or x1 > pr.width - BLEED or y1 > pr.height - BLEED:
            out_of_bleed.append({**bl, "overflow": {
                "left": round(max(0, BLEED - x0),2), "top": round(max(0, BLEED - y0),2),
                "right": round(max(0, x1 - (pr.width - BLEED)),2), "bottom": round(max(0, y1 - (pr.height - BLEED)),2)}})
        if x0 < MARGIN_L - 1 or y0 < MARGIN_T - 1 or x1 > pr.width - MARGIN_R + 1 or y1 > pr.height - MARGIN_B + 1:
            out_of_margin.append(bl)

    overlaps = []
    n = len(blocks)
    for a in range(n):
        for b in range(a + 1, n):
            A, B = blocks[a], blocks[b]
            ax0, ay0, ax1, ay1 = A["bbox"]; bx0, by0, bx1, by1 = B["bbox"]
            ix0, iy0 = max(ax0, bx0), max(ay0, by0)
            ix1, iy1 = min(ax1, bx1), min(ay1, by1)
            if ix1 <= ix0 or iy1 <= iy0:
                continue
            inter = (ix1 - ix0) * (iy1 - iy0)
            areaA = max(1e-6, (ax1 - ax0) * (ay1 - ay0))
            areaB = max(1e-6, (bx1 - bx0) * (by1 - by0))
            ratio = inter / min(areaA, areaB)
            if inter >= OVERLAP_MIN and ratio >= OVERLAP_RATIO:
                overlaps.append({"a": A["preview"][:40], "b": B["preview"][:40],
                                 "area_pt2": round(inter, 2), "ratio_of_smaller": round(ratio, 3),
                                 "rect": [round(ix0,2), round(iy0,2), round(ix1,2), round(iy1,2)]})

    pages_out.append({
        "page": i + 1,
        "page_size_pt": [round(pr.width,2), round(pr.height,2)],
        "block_count": len(blocks),
        "out_of_bleed_count": len(out_of_bleed),
        "out_of_margin_count": len(out_of_margin),
        "out_of_bleed": out_of_bleed[:12],
        "out_of_margin_sample": out_of_margin[:8],
        "overlap_count": len(overlaps),
        "overlaps": overlaps[:12],
    })

doc.close()
payload = {"pdf": pdf_path, "page_count": len(pages_out),
           "thresholds": {"bleed_pt": BLEED, "margin_pt": [MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B],
                          "overlap_min_area_pt2": OVERLAP_MIN, "overlap_min_ratio": OVERLAP_RATIO},
           "pages": pages_out}
with open(sys.argv[2], "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False, indent=1)
print("OK pages=%d" % len(pages_out))
