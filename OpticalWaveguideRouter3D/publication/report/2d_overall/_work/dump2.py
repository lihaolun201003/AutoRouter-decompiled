
import csv, json, pathlib
root = pathlib.Path(r"C:\Users\lihao\Desktop\Graduation Project")
files = [
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/256/protection_margins.csv",
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/512/protection_margins.csv",
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/256/probe/probe_summary.csv",
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/512/probe/probe_summary.csv",
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/256/protection_set.json",
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/512/protection_set.json",
 "OpticalWaveguideRouter3D/outputs/opt2d_step13_fix/legacy_scheme_scan.csv",
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/256/optimize_record.json",
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/512/optimize_record.json",
 "OpticalWaveguideRouter3D/outputs/opt2d_step13_fix/256/acceptance.json",
 "OpticalWaveguideRouter3D/outputs/opt2d_step13_fix/512/acceptance.json",
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/256/radius_freeze_check.csv",
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/512/radius_freeze_check.csv",
]
for f in files:
    p = root / f
    print("="*8, f)
    if not p.exists():
        print("  MISSING"); continue
    if p.suffix == ".json":
        print(json.dumps(json.loads(p.read_text(encoding="utf-8-sig")), ensure_ascii=False, indent=1)[:2200]); continue
    with open(p, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    for r in rows[:14]:
        print(" | ".join(r))
    if len(rows) > 14: print("   ... (%d rows total)" % len(rows))
