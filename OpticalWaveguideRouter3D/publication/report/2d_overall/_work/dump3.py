
import json, pathlib
root = pathlib.Path(r"C:\Users\lihao\Desktop\Graduation Project")
for f in ["OpticalWaveguideRouter2D/results/fiberBoard256_loss_summary.json",
          "OpticalWaveguideRouter2D/results/fiberBoard512_loss_summary.json",
          "OpticalWaveguideRouter2D/results/fiberBoard512_loss_R2_summary.json"]:
    p = root/f
    print("="*6, f)
    d = json.loads(p.read_text(encoding="utf-8-sig"))
    print(json.dumps(d, ensure_ascii=False, indent=1)[:2600])
