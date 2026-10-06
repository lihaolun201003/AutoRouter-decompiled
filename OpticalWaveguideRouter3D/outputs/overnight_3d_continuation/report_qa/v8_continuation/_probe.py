# -*- coding: utf-8 -*-
"""Read-only probe: page-2 table rows (by y) + full image inventory."""
import sys, json, fitz
doc = fitz.open(sys.argv[1])

print("=== P2 table rows (words grouped by y band 380..840pt) ===")
p = doc[1]
rows = {}
for w in p.get_text("words"):
    if 380 < w[1] < 840:
        rows.setdefault(round(w[1] / 3.0), []).append(w)
for k in sorted(rows):
    print("%6.1f | %s" % (k * 3, " ".join(w[4] for w in sorted(rows[k], key=lambda x: x[0]))))

print()
print("=== IMAGE INVENTORY ===")
tot = 0
for i in range(doc.page_count):
    for im in doc[i].get_image_info():
        bb = im["bbox"]
        wpt, hpt = bb[2] - bb[0], bb[3] - bb[1]
        tot += 1
        print("p%02d x0=%7.1f y0=%7.1f w=%6.1fpt h=%6.1fpt src=%dx%d eff_dpi=%.0f"
              % (i + 1, bb[0], bb[1], wpt, hpt, im["width"], im["height"], im["width"] / (wpt / 72.0)))
print("total images =", tot)

print()
print("=== per-page vertical content extent (text+image) vs 792pt page ===")
for i in range(doc.page_count):
    p = doc[i]
    ymax, ymin = 0.0, 792.0
    for b in p.get_text("blocks"):
        if b[4].strip():
            ymax = max(ymax, b[3]); ymin = min(ymin, b[1])
    for im in p.get_image_info():
        ymax = max(ymax, im["bbox"][3]); ymin = min(ymin, im["bbox"][1])
    # last-ink row via pixel-free heuristic only
    print("p%02d first_ink_y=%6.1f last_ink_y=%6.1f bottom_blank=%6.1fpt (%.0f%% of page)"
          % (i + 1, ymin, ymax, 792 - ymax, (792 - ymax) / 792 * 100))
doc.close()
