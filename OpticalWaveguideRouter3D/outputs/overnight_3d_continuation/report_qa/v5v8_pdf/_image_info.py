# -*- coding: utf-8 -*-
import sys, json, fitz
d = fitz.open(sys.argv[1])
rows = []
for i in range(d.page_count):
    p = d[i]
    for im in p.get_image_info(xrefs=True):
        bb = im.get("bbox")
        if not bb: continue
        w_pt, h_pt = bb[2]-bb[0], bb[3]-bb[1]
        pw, ph = im.get("width"), im.get("height")
        rows.append({"page": i+1, "xref": im.get("xref"), "px": [pw, ph],
                     "placed_pt": [round(w_pt,1), round(h_pt,1)],
                     "eff_dpi": [round(pw/(w_pt/72.0),1) if w_pt else None,
                                 round(ph/(h_pt/72.0),1) if h_pt else None]})
with open(sys.argv[2], "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=1)
print("images", len(rows))
