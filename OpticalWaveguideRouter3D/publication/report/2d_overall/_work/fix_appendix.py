
import sys, pathlib, json
sys.stdout.reconfigure(encoding="utf-8")
p = pathlib.Path(r"C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D\publication\report\2d_overall") / "二维光波导自动布线总体实验报告.md"
t = p.read_text(encoding="utf-8")
start = t.index("表61 二维实验总表")
end = t.index("<!-- pagebreak -->", start)
seg = t[start:end]
seg2 = seg.replace("OpticalWaveguideRouter2D/", "2D/").replace("OpticalWaveguideRouter3D/", "3D/")
seg2 = seg2.replace("\`3D/publication/tables/", "\`t").replace("_data.csv\`", "\`")
seg2 = seg2.replace("3D/publication/", "").replace("3D/docs/reports/", "").replace("3D/docs/2d_routing/", "")
t = t[:start] + seg2 + t[end:]
t = t.replace("本表把本报告覆盖的全部二维实验按\"研究问题\"列出。",
              "本表把本报告覆盖的全部二维实验按\"研究问题\"列出。表中 **2D = OpticalWaveguideRouter2D，3D = OpticalWaveguideRouter3D**；省略 3D/docs/reports/ 前缀。")
p.write_text(t, encoding="utf-8")
print("appendix A shortened")
# report widths config
w = pathlib.Path(r"C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D\publication\report\2d_overall/_work") / "table_cols.json"
cfg = {
 "表61 二维": [2.0, 1.7, 1.9, 1.7, 2.4, 1.9, 2.6],
 "表39 冻结": [2.6, 1.3, 1.2, 1.2, 1.2, 1.6, 0.85, 0.95, 1.0, 1.3, 1.2],
 "表40 冻结": [2.6, 1.3, 1.2, 1.2, 1.2, 1.6, 0.85, 0.95, 1.0, 1.3, 1.2],
 "表16 候选": [1.0, 0.95, 1.25, 1.25, 1.25, 1.25, 1.0, 2.0, 1.35, 1.25, 1.2, 1.2],
 "表22 固定": [0.95, 1.2, 1.2, 1.15, 1.15, 1.15, 0.9, 2.3, 1.25, 1.15, 1.05, 1.05, 1.0, 1.05],
 "表23 固定": [0.95, 1.2, 1.2, 1.15, 1.15, 1.15, 0.9, 2.3, 1.25, 1.15, 1.05, 1.05, 1.0, 1.05],
 "表45 压力": [1.0, 1.3, 1.3, 1.3, 1.3, 1.3],
 "表66 正文": [2.2, 3.4, 10.8],
 "表67 正文": [1.2, 5.4, 9.8],
 "表55 排序": [3.2, 3.0, 2.0, 4.4, 1.9, 3.3],
 "表14 512 ": [1.2, 1.5, 1.6, 1.6, 1.7, 1.6, 2.2, 2.3],
}
w.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
print("widths written:", len(cfg))
