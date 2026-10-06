# -*- coding: utf-8 -*-
"""Count ASCII/identifier tokens that are wrapped in the MIDDLE of the token.

A real in-cell wrap = two consecutive lines INSIDE THE SAME text block (same table
cell), where the first ends with [A-Za-z0-9_] and the second starts with [A-Za-z0-9_]
and the second line's left edge is (almost) the same x as the first's.
Adjacent table cells are different blocks, so they are not counted.
"""
import json, re, sys
import fitz
sys.stdout.reconfigure(encoding="utf-8")
PDF = r"C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D\publication\report\三维布线v8路径弧长窗口续跑报告.pdf"
doc = fitz.open(PDF)
per_page, samples = {}, []
total = 0
for i, page in enumerate(doc):
    hits = []
    for blk in page.get_text("dict")["blocks"]:
        if blk.get("type") != 0:
            continue
        lines = []
        for ln in blk["lines"]:
            t = "".join(s["text"] for s in ln["spans"])
            if t.strip():
                lines.append((t, ln["bbox"]))
        for (a, ba), (b, bb) in zip(lines, lines[1:]):
            if a[-1] == " " or b[0] == " ":
                continue
            if not (re.search(r"[A-Za-z0-9_]$", a) and re.match(r"[A-Za-z0-9_]", b)):
                continue
            if abs(ba[0] - bb[0]) > 2.0:
                continue
            if bb[1] - ba[3] > 6.0 or bb[1] < ba[1]:
                continue
            hits.append({"a": a.strip(), "b": b.strip(), "y": round(ba[1], 1), "x": round(ba[0], 1)})
    total += len(hits)
    per_page[i + 1] = hits
    if hits:
        samples.append("p%02d n=%d  " % (i + 1, len(hits)) + " | ".join("%s+%s" % (h["a"][-24:], h["b"][:12]) for h in hits[:8]))
doc.close()
print("\n".join(samples))
print("TOTAL in-cell ASCII token wraps:", total)
print("pages affected:", sorted(k for k, v in per_page.items() if v))
json.dump({str(k): v for k, v in per_page.items() if v}, open(r"C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D\outputs\overnight_3d_continuation\report_qa\v8_continuation_fixed\ascii_break_scan.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
