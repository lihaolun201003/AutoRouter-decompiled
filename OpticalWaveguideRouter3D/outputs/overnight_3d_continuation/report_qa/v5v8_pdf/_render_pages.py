# -*- coding: utf-8 -*-
"""Render every PDF page to PNG. Read-only on the source PDF."""
import sys, os, json
import fitz

pdf_path = sys.argv[1]
out_dir = sys.argv[2]
dpi = int(sys.argv[3]) if len(sys.argv) > 3 else 140

os.makedirs(out_dir, exist_ok=True)
doc = fitz.open(pdf_path)
zoom = dpi / 72.0
mat = fitz.Matrix(zoom, zoom)
info = []
for i in range(doc.page_count):
    page = doc[i]
    pix = page.get_pixmap(matrix=mat, alpha=False)
    name = "page_%02d.png" % (i + 1)
    path = os.path.join(out_dir, name)
    pix.save(path)
    info.append({
        "page": i + 1,
        "image": name,
        "width_px": pix.width,
        "height_px": pix.height,
        "bytes": os.path.getsize(path),
        "rotation": page.rotation,
        "text_chars": len(page.get_text("text").strip()),
    })
doc.close()
print(json.dumps({"pdf": pdf_path, "dpi": dpi, "page_count": len(info), "pages": info}, ensure_ascii=False))
