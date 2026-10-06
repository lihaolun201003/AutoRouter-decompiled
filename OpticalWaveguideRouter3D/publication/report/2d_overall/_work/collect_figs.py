
import shutil, pathlib, json
from PIL import Image
root = pathlib.Path(r"C:\Users\lihao\Desktop\Graduation Project")
dst = root/"OpticalWaveguideRouter3D/publication/report/2d_overall/figures"
dst.mkdir(parents=True, exist_ok=True)
items = [
 ("f32_reproduction_accuracy","OpticalWaveguideRouter3D/publication/figures/f32_reproduction_accuracy.png"),
 ("f33_radius_sweep_512","OpticalWaveguideRouter3D/publication/figures/f33_radius_sweep_512.png"),
 ("f34_loss_contribution_repro","OpticalWaveguideRouter3D/publication/figures/f34_loss_contribution_repro.png"),
 ("f37_crossing_angle_distribution","OpticalWaveguideRouter3D/publication/figures/f37_crossing_angle_distribution.png"),
 ("f38_legacy_geometric_audit","OpticalWaveguideRouter3D/publication/figures/f38_legacy_geometric_audit.png"),
 ("f39_legacy_bytecode_check","OpticalWaveguideRouter3D/publication/figures/f39_legacy_bytecode_check.png"),
 ("f310_crossing_model_sensitivity","OpticalWaveguideRouter3D/publication/figures/f310_crossing_model_sensitivity.png"),
 ("f51_step12_main","OpticalWaveguideRouter3D/publication/figures/f51_step12_main.png"),
 ("f52_step12_loss_breakdown","OpticalWaveguideRouter3D/publication/figures/f52_step12_loss_breakdown.png"),
 ("f53_step12_ablation","OpticalWaveguideRouter3D/publication/figures/f53_step12_ablation.png"),
 ("f54_step12_efficiency","OpticalWaveguideRouter3D/publication/figures/f54_step12_efficiency.png"),
 ("f61_step13_main","OpticalWaveguideRouter3D/publication/figures/f61_step13_main.png"),
 ("f62_step13_breakdown","OpticalWaveguideRouter3D/publication/figures/f62_step13_breakdown.png"),
 ("f63_step13_worst_route","OpticalWaveguideRouter3D/publication/figures/f63_step13_worst_route.png"),
 ("f64_step13_fix_delta","OpticalWaveguideRouter3D/publication/figures/f64_step13_fix_delta.png"),
 ("f65_step13_constrained","OpticalWaveguideRouter3D/publication/figures/f65_step13_constrained.png"),
 ("f66_step13_sensitivity","OpticalWaveguideRouter3D/publication/figures/f66_step13_sensitivity.png"),
 ("f67_step13_penalty_ablation","OpticalWaveguideRouter3D/publication/figures/f67_step13_penalty_ablation.png"),
 ("f71_step14_main","OpticalWaveguideRouter3D/publication/figures/f71_step14_main.png"),
 ("f72_step14_scenario5","OpticalWaveguideRouter3D/publication/figures/f72_step14_scenario5.png"),
 ("f73_step14_small_angle","OpticalWaveguideRouter3D/publication/figures/f73_step14_small_angle.png"),
 ("f74_step14_protection_delta","OpticalWaveguideRouter3D/publication/figures/f74_step14_protection_delta.png"),
 ("f75_step14_optimize_process","OpticalWaveguideRouter3D/publication/figures/f75_step14_optimize_process.png"),
 ("f76_step14_probe_variants","OpticalWaveguideRouter3D/publication/figures/f76_step14_probe_variants.png"),
 ("f77_step14_sensitivity","OpticalWaveguideRouter3D/publication/figures/f77_step14_sensitivity.png"),
 ("layout_256_r5","OpticalWaveguideRouter2D/results/fiberBoard256bend.png"),
 ("layout_512_r5","OpticalWaveguideRouter2D/results/fiberBoard512bend.png"),
 ("legacy512_centerlines","OpticalWaveguideRouter3D/outputs/step_8_5_legacy_512_smoothed.png"),
 ("opt2d_256_metric","OpticalWaveguideRouter3D/outputs/opt2d/256/figures/metric_comparison.png"),
 ("opt2d_512_metric","OpticalWaveguideRouter3D/outputs/opt2d/512/figures/metric_comparison.png"),
]
res = []
for name, rel in items:
    src = root/rel
    if not src.is_file():
        res.append({"name":name,"rel":rel,"status":"MISSING"}); continue
    out = dst/(name+".png")
    if src.resolve() != out.resolve(): shutil.copy2(src, out)
    with Image.open(out) as im:
        w,h = im.size
    res.append({"name":name,"rel":rel,"status":"ok","w":w,"h":h,"ratio":round(w/h,3),"bytes":out.stat().st_size})
print(json.dumps(res, ensure_ascii=False, indent=1))
