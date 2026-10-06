
import csv, json, pathlib, sys
root = pathlib.Path(r"C:\Users\lihao\Desktop\Graduation Project")
files = [
 "OpticalWaveguideRouter3D/publication/tables/t31_bend_model_thesis_vs_repro_data.csv",
 "OpticalWaveguideRouter3D/publication/tables/t32_reproduction_compare_data.csv",
 "OpticalWaveguideRouter3D/publication/tables/t33_radius_sweep_512_data.csv",
 "OpticalWaveguideRouter3D/publication/tables/t34_crossing_model_sensitivity_data.csv",
 "OpticalWaveguideRouter3D/publication/tables/t51_step12_main_data.csv",
 "OpticalWaveguideRouter3D/publication/tables/t52_step12_ablation_data.csv",
 "OpticalWaveguideRouter3D/publication/tables/t61_step13_main_data.csv",
 "OpticalWaveguideRouter3D/publication/tables/t62_step13_cost_data.csv",
 "OpticalWaveguideRouter3D/publication/tables/t63_step13_constrained_data.csv",
 "OpticalWaveguideRouter3D/publication/tables/t64_step13_sensitivity_data.csv",
 "OpticalWaveguideRouter3D/publication/tables/t71_step14_main_data.csv",
 "OpticalWaveguideRouter3D/publication/tables/t72_step14_scenario_data.csv",
 "OpticalWaveguideRouter3D/publication/tables/t73_step14_optimize_data.csv",
 "OpticalWaveguideRouter3D/publication/tables/t74_step14_sensitivity_data.csv",
 "OpticalWaveguideRouter3D/outputs/opt2d/256/comparison.csv",
 "OpticalWaveguideRouter3D/outputs/opt2d/512/comparison.csv",
 "OpticalWaveguideRouter3D/outputs/opt2d_step13_fix/256/comparison.csv",
 "OpticalWaveguideRouter3D/outputs/opt2d_step13_fix/512/comparison.csv",
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/256/comparison.csv",
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/512/comparison.csv",
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/256/acceptance.csv",
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/512/acceptance.csv",
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/256/references.csv",
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/512/references.csv",
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/256/protection_margins.csv",
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/512/protection_margins.csv",
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/256/probe/probe_summary.csv",
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/512/probe/probe_summary.csv",
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/256/protection_set.json",
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/512/protection_set.json",
 "OpticalWaveguideRouter3D/outputs/opt2d_step13_fix/legacy_scheme_scan.csv",
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/256/optimize_record.json",
 "OpticalWaveguideRouter3D/outputs/opt2d_step14/512/optimize_record.json",
]
for f in files:
    p = root / f
    print("="*8, f)
    if not p.exists():
        print("  MISSING"); continue
    if p.suffix == ".json":
        print(json.dumps(json.loads(p.read_text(encoding="utf-8-sig")), ensure_ascii=False, indent=1)[:2500]); continue
    with open(p, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    for r in rows:
        print(" | ".join(r))
