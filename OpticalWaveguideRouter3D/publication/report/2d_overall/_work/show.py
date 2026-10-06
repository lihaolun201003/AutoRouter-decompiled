
import json, pathlib, sys
sys.stdout.reconfigure(encoding="utf-8")
p = pathlib.Path(r"C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D\publication\report\2d_overall\_work/facts_step14.json")
d = json.loads(p.read_text(encoding="utf-8"))
print("--- corrections ---")
print(json.dumps(d.get("corrections",[]), ensure_ascii=False, indent=1)[:5000])
print("--- unverified ---")
print(json.dumps(d.get("unverified",[]), ensure_ascii=False, indent=1)[:3000])
