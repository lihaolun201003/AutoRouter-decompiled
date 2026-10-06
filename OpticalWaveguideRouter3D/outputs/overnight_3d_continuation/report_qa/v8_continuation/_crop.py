# -*- coding: utf-8 -*-
"""Zoom a fractional region of a rendered page PNG. Writes NEW files only."""
import sys
from PIL import Image
src, out, x0, y0, x1, y1, scale = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]), float(sys.argv[6]), float(sys.argv[7])
im = Image.open(src)
W, H = im.size
box = (int(W*x0), int(H*y0), int(W*x1), int(H*y1))
c = im.crop(box)
c = c.resize((int(c.width*scale), int(c.height*scale)), Image.LANCZOS)
c.save(out)
print("%s crop=%s -> %dx%d" % (out, box, c.width, c.height))
