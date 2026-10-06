# -*- coding: utf-8 -*-
"""Render a clipped region of a PDF page at high zoom for close inspection."""
import sys, fitz
pdf, page_no, x0, y0, x1, y1, zoom, out = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]), float(sys.argv[6]), float(sys.argv[7]), sys.argv[8]
d = fitz.open(pdf)
p = d[page_no - 1]
clip = fitz.Rect(x0, y0, x1, y1)
pix = p.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
pix.save(out)
print("saved %s %dx%d" % (out, pix.width, pix.height))
