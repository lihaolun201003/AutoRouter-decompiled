# -*- coding: utf-8 -*-
import sys, json, io, re
import fitz
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
d = fitz.open(sys.argv[1])
for i in range(15, d.page_count):
    p = d[i]
    items = []
    for im in p.get_image_info():
        bb = im.get("bbox")
        if bb: items.append((round(bb[1],1), round(bb[3],1), "IMG", "%dx%d" % (im.get("width"), im.get("height"))))
    for b in p.get_text("blocks"):
        t = (b[4] or "").strip().replace("\n", " ")
        if not t: continue
        items.append((round(b[1],1), round(b[3],1), "TXT", t[:95]))
    items.sort()
    print("===== PAGE %d =====" % (i+1))
    for y0, y1, kind, t in items:
        print("  y%7.1f-%7.1f %-4s %s" % (y0, y1, kind, t))
