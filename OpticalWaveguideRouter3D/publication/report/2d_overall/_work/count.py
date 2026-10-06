
import re, sys, pathlib
sys.stdout.reconfigure(encoding="utf-8")
p = pathlib.Path(r"C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D\publication\report\2d_overall") / "二维光波导自动布线总体实验报告.md"
t = p.read_text(encoding="utf-8")
lines = t.split("\n")
print("lines", len(lines), "chars", len(t))
sep = [i for i,l in enumerate(lines) if re.match(r"^\|\s*-{3,}", l)]
print("tables(separators):", len(sep))
print("figures:", sum(1 for l in lines if l.startswith("![")))
print("h1:", sum(1 for l in lines if re.match(r"^# ", l)))
print("h2:", sum(1 for l in lines if re.match(r"^## ", l)))
print("h3:", sum(1 for l in lines if re.match(r"^### ", l)))
print("captioned tables:", sum(1 for l in lines if re.match(r"^表", l.strip())))
for i in sep:
    hdr = lines[i-1].strip()
    prev = lines[i-2].strip()
    print(i, "|", prev[:50], "||", hdr[:60])
