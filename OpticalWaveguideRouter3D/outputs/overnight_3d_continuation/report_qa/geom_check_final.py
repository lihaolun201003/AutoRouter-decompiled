"""Machine geometry check of the final continuation report (text blocks + images).

This is the MACHINE half of the visual QA: it finds text blocks that overflow the
printable area and text blocks that overlap. It cannot see overlaps INSIDE a
raster figure, which is why the page-by-page visual inspection is recorded
separately.

Usage: python -B outputs/overnight_3d_continuation/report_qa/geom_check_final.py PDF OUTJSON
"""
import json
import sys

import fitz

pdf_path, out_path = sys.argv[1], sys.argv[2]
document = fitz.open(pdf_path)
margins = 54.0
rows = []
for index in range(document.page_count):
    page = document[index]
    width, height = page.rect.width, page.rect.height
    blocks = [b for b in page.get_text("blocks") if b[6] == 0 and b[4].strip()]
    images = page.get_image_info()
    overflow = []
    for b in blocks:
        x0, y0, x1, y1 = b[:4]
        if x0 < margins - 1 or y0 < margins - 1 or x1 > width - margins + 1 or y1 > height - margins + 1:
            overflow.append(dict(text=b[4][:40], rect=[round(v, 1) for v in b[:4]]))
    overlaps = []
    for i in range(len(blocks)):
        for j in range(i + 1, len(blocks)):
            a, b = blocks[i], blocks[j]
            rect_a = fitz.Rect(a[:4]); rect_b = fitz.Rect(b[:4])
            inter = rect_a & rect_b
            if inter.is_empty or inter.get_area() <= 0:
                continue
            smaller = min(rect_a.get_area(), rect_b.get_area())
            if smaller and inter.get_area() / smaller > 0.25:
                overlaps.append(dict(a=a[4][:40], b=b[4][:40],
                                     frac_of_smaller=round(inter.get_area() / smaller, 2),
                                     rect=[round(v, 1) for v in inter]))
    rows.append(dict(page=index + 1, page_size_pt=[width, height], text_blocks=len(blocks),
                     images=len(images),
                     image_assets=[img.get("digest") for img in images],
                     char_count=len(page.get_text().strip()),
                     overflow_blocks=overflow, overlapping_block_pairs=overlaps))
document.close()
summary = dict(pdf=pdf_path, pages=len(rows),
               method="PyMuPDF get_text('blocks') + get_image_info; margins 54 pt",
               limits=("this check cannot detect text overlapping inside a raster figure; "
                       "those findings come from the page-by-page visual inspection"),
               totals=dict(overflow=sum(len(r["overflow_blocks"]) for r in rows),
                           overlaps=sum(len(r["overlapping_block_pairs"]) for r in rows),
                           pages_with_images=sum(1 for r in rows if r["images"])),
               page_checks=rows)
with open(out_path, "w", encoding="utf-8") as handle:
    json.dump(summary, handle, indent=2)
print(json.dumps(summary["totals"], indent=2))
for row in rows:
    if row["overflow_blocks"] or row["overlapping_block_pairs"]:
        print("page", row["page"], "overflow", len(row["overflow_blocks"]),
              "overlaps", len(row["overlapping_block_pairs"]))
