# -*- coding: utf-8 -*-
"""Read-only: image inventory + per-page ink extent -> JSON."""
import sys, json, fitz
doc = fitz.open(sys.argv[1])
out = {"pdf": sys.argv[1], "page_count": doc.page_count, "page_pt": [doc[0].rect.width, doc[0].rect.height], "images": [], "extent": []}
for i in range(doc.page_count):
    p = doc[i]
    for im in p.get_image_info():
        bb = im["bbox"]; wpt = bb[2] - bb[0]
        out["images"].append({"page": i + 1, "bbox": [round(v, 1) for v in bb],
                              "w_pt": round(wpt, 1), "h_pt": round(bb[3] - bb[1], 1),
                              "src": "%dx%d" % (im["width"], im["height"]),
                              "eff_dpi": round(im["width"] / (wpt / 72.0))})
    ymin, ymax = 792.0, 0.0
    for b in p.get_text("blocks"):
        if b[4].strip():
            ymin = min(ymin, b[1]); ymax = max(ymax, b[3])
    for im in p.get_image_info():
        ymin = min(ymin, im["bbox"][1]); ymax = max(ymax, im["bbox"][3])
    out["extent"].append({"page": i + 1, "first_ink_y": round(ymin, 1), "last_ink_y": round(ymax, 1),
                          "bottom_blank_pt": round(792 - ymax, 1), "bottom_blank_pct": round((792 - ymax) / 792 * 100)})
json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("images=%d pages=%d" % (len(out["images"]), doc.page_count))
doc.close()
