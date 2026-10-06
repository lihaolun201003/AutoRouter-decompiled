# -*- coding: utf-8 -*-
"""Read-only page metadata: text preview, image inventory, table/caption hints."""
import sys, json, fitz
doc = fitz.open(sys.argv[1])
out = []
for i in range(doc.page_count):
    p = doc[i]
    txt = p.get_text("text")
    lines = [l for l in txt.split("\n") if l.strip()]
    imgs = []
    for im in p.get_image_info():
        bb = im.get("bbox")
        imgs.append({"bbox": [round(v,1) for v in bb] if bb else None,
                     "w": im.get("width"), "h": im.get("height"),
                     "eff_dpi": round(im.get("width",0) / max(1e-6,(bb[2]-bb[0])/72.0)) if bb else None})
    drawings = len(p.get_drawings())
    out.append({"page": i+1, "lines": len(lines), "chars": len(txt.strip()),
                "first5": lines[:5], "last5": lines[-5:],
                "images": imgs, "drawings": drawings,
                "blocks": len([b for b in p.get_text("blocks") if b[4].strip()])})
doc.close()
json.dump(out, open(sys.argv[2],"w",encoding="utf-8"), ensure_ascii=False, indent=1)
print("OK")
