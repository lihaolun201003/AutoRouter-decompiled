# -*- coding: utf-8 -*-
import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
d = json.load(open(sys.argv[1], encoding='utf-8'))
print("thr", json.dumps(d["thresholds"]))
print("pg |blk|bleed|marg|ovl| detail")
for p in d["pages"]:
    det = []
    for o in p["out_of_bleed"]:
        det.append("BLEED[%s] bbox=%s ov=%s" % (o["type"], o["bbox"], o.get("overflow")))
    for o in p["overlaps"]:
        det.append("OVL area=%.1f ratio=%.2f rect=%s a=%r b=%r" % (o["area_pt2"], o["ratio_of_smaller"], o["rect"], o["a"], o["b"]))
    for o in p["out_of_margin_sample"]:
        det.append("MARGIN[%s] bbox=%s %r" % (o["type"], o["bbox"], o["preview"][:26]))
    print("%2d |%3d|%5d|%4d|%3d| %s" % (p["page"], p["block_count"], p["out_of_bleed_count"], p["out_of_margin_count"], p["overlap_count"], " ;; ".join(det)))
