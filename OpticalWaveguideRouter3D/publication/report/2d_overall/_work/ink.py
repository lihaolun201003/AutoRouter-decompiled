
import sys, pathlib
sys.stdout.reconfigure(encoding="utf-8")
from PIL import Image
d = pathlib.Path(r"C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D\publication\report\2d_overall/_work/render_all")
rows = []
for p in sorted(d.glob("page-*.png")):
    im = Image.open(p).convert("L")
    w,h = im.size
    px = im.load()
    dark = 0; colored = 0
    step = 2
    tot = 0
    for y in range(0,h,step):
        for x in range(0,w,step):
            v = px[x,y]; tot += 1
            if v < 200: dark += 1
    rows.append((p.name, round(100*dark/tot,2)))
print("pages:", len(rows))
blank = [r for r in rows if r[1] < 0.8]
print("near-blank pages (<0.8% ink):", blank)
print("min ink:", min(rows, key=lambda r: r[1]))
print("max ink:", max(rows, key=lambda r: r[1]))
# print density profile in rows of 10
for i in range(0, len(rows), 10):
    print(" ".join("%s:%.1f" % (n.split("-")[1].split(".")[0], v) for n, v in rows[i:i+10]))
