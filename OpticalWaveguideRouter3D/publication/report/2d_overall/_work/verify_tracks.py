
import sys, openpyxl, pathlib
from collections import Counter
sys.stdout.reconfigure(encoding="utf-8")
root = pathlib.Path(r"C:\Users\lihao\Desktop\Graduation Project/OpticalWaveguideRouter2D/results")
for name, pitch, lo, hi in [("fiberBoard256bend.xlsx",0.30,5.0,144.8),("fiberBoard512bend.xlsx",0.175,5.0,144.825)]:
    wb = openpyxl.load_workbook(root/name, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(c) for c in rows[0]]
    print("==", name, "rows", len(rows)-1, "cols", len(hdr))
    print("header:", hdr)
    i = hdr.index("inflection") if "inflection" in hdr else 0
    vals = [r[i] for r in rows[1:] if r[i] is not None]
    c = Counter(vals)
    used = len(c)
    cand = round((hi-lo)/pitch)+1
    shared = sum(1 for k,v in c.items() if v>1)
    routes_on_shared = sum(v for k,v in c.items() if v>1)
    print("routes:", len(vals), "used tracks:", used, "candidate tracks:", cand,
          "tracks used by >1 route:", shared, "routes on shared tracks:", routes_on_shared)
    print("min/max inflection:", min(vals), max(vals))
    # dx>=2R split
    if "dx" in hdr:
        j = hdr.index("dx")
        dx = [float(r[j]) for r in rows[1:] if r[j] is not None]
        R = 5.0
        print("dx<2R routes:", sum(1 for d in dx if 0 < d < 2*R), " dx==0:", sum(1 for d in dx if d==0),
              " dx>=2R:", sum(1 for d in dx if d>=2*R))
