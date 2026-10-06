# -*- coding: utf-8 -*-
"""Classify geometry 'overlaps' into containment (nested block) vs partial overlap."""
import sys, json
g = json.load(open(sys.argv[1], encoding="utf-8"))
out = {"thresholds": g["thresholds"], "pages": []}
tot_cont = tot_part = 0
for p in g["pages"]:
    cont = [o for o in p["overlaps"] if o["ratio_of_smaller"] >= 0.95]
    part = [o for o in p["overlaps"] if o["ratio_of_smaller"] < 0.95]
    tot_cont += len(cont); tot_part += len(part)
    out["pages"].append({"page": p["page"], "blocks": p["block_count"],
                         "out_of_bleed": p["out_of_bleed_count"], "out_of_margin": p["out_of_margin_count"],
                         "overlaps_total": p["overlap_count"],
                         "overlaps_containment": len(cont), "overlaps_partial": len(part),
                         "partial_detail": part[:6]})
out["totals"] = {"bleed": sum(p["out_of_bleed_count"] for p in g["pages"]),
                 "margin": sum(p["out_of_margin_count"] for p in g["pages"]),
                 "overlaps": sum(p["overlap_count"] for p in g["pages"]),
                 "containment": tot_cont, "partial": tot_part}
json.dump(out, open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("containment=%d partial=%d" % (tot_cont, tot_part))
for pg in out["pages"]:
    if pg["overlaps_partial"]:
        print("p%02d partial=%d" % (pg["page"], pg["overlaps_partial"]))
        for d in pg["partial_detail"]:
            print("   ratio=%.2f area=%.0f A=%r B=%r" % (d["ratio_of_smaller"], d["area_pt2"], d["a"][:30], d["b"][:30]))
