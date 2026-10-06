# -*- coding: utf-8 -*-
"""Crop each embedded figure (+ its caption line) at 300 DPI straight from the PDF."""
import json, sys, os
import fitz
sys.stdout.reconfigure(encoding="utf-8")
PDF = r"C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D\publication\report\三维布线v8路径弧长窗口续跑报告.pdf"
OUT = os.path.dirname(os.path.abspath(__file__))
doc = fitz.open(PDF)
info, n = [], 0
for pno in range(doc.page_count):
    page = doc[pno]
    imgs = sorted(page.get_image_info(), key=lambda i: i["bbox"][1])
    for im in imgs:
        n += 1
        x0, y0, x1, y1 = im["bbox"]
        clip = fitz.Rect(max(0, x0 - 8), max(0, y0 - 4), min(page.rect.x1, x1 + 8), min(page.rect.y1, y1 + 48))
        pix = page.get_pixmap(clip=clip, matrix=fitz.Matrix(300 / 72, 300 / 72))
        name = "figcrop_%02d_p%02d.png" % (n, pno + 1)
        pix.save(os.path.join(OUT, name))
        info.append({"fig": n, "page": pno + 1, "clip_pt": [round(v, 1) for v in clip],
                     "native_px": [im["width"], im["height"]], "crop_px": [pix.width, pix.height],
                     "effective_dpi_in_pdf": round(im["width"] / ((x1 - x0) / 72), 1), "file": name})
doc.close()
json.dump(info, open(os.path.join(OUT, "figure_crops.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for i in info:
    print(i["fig"], "p%d" % i["page"], "native", i["native_px"], "dpi", i["effective_dpi_in_pdf"], "crop", i["crop_px"], i["file"])
