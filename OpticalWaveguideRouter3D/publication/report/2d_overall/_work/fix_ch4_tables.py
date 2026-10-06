
import sys, pathlib, json
sys.stdout.reconfigure(encoding="utf-8")
md = pathlib.Path(r"C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D\publication\report\2d_overall") / "二维光波导自动布线总体实验报告.md"
lines = md.read_text(encoding="utf-8").split("\n")
OLD = "| 方案 | 完整连接 | 端点变化 | 平均（dB） | P95（dB） | 最大（dB） | 最差路线 | 直线/弯曲/交叉均值（dB） | 平均总弯角 | 唯一交叉 | <10° 交叉 | 间距违规 | 重合 | 段级接触 | 运行（s） |"
NEW = "| 方案 | 完整连接 | 平均（dB） | P95（dB） | 最大（dB） | 最差路线 | 直线/弯曲/交叉（dB） | 平均总弯角 | 唯一交叉 | <10° | 间距违规 | 段级接触 | 运行（s） |"
out=[];i=0;hits=0
while i < len(lines):
    if lines[i].strip()==OLD:
        hits+=1
        out.append(NEW)
        out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        i+=2
        while i < len(lines) and lines[i].lstrip().startswith("|"):
            cells=[c.strip() for c in lines[i].strip().strip("|").split("|")]
            # drop 端点变化 (idx2) and 重合 (idx12) from the 15-cell row
            keep=[c for j,c in enumerate(cells) if j not in (2,12)]
            out.append("| " + " | ".join(keep) + " |")
            i+=1
        out.append("")
        out.append("注：全部方案的端点变化与重合计数均为 0，故不单列；段级接触的口径见 5.2.1 节。半径分布为 D0 在 512 上 R6×502 + R5×10，D56 与 F56 为 R6×510 + R5×2，F5 全部 R5。")
        continue
    out.append(lines[i]); i+=1
print("restructured:", hits)
assert hits==2
md.write_text("\n".join(out), encoding="utf-8")
w = pathlib.Path(r"C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D\publication\report\2d_overall/_work") / "table_cols.json"
cfg = json.loads(w.read_text(encoding="utf-8"))
cfg["表22 固定"] = [2.0,1.15,1.1,1.1,1.1,1.0,2.1,1.2,1.15,0.85,1.15,1.15,1.0]
cfg["表23 固定"] = cfg["表22 固定"]
w.write_text(json.dumps(cfg, ensure_ascii=False, indent=1), encoding="utf-8")
print("widths set")
