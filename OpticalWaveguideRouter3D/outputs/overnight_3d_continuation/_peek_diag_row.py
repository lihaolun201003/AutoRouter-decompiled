
import json
from pathlib import Path
d=json.loads(Path(r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D/outputs/overnight_3d_continuation/diagnostics/v8_side_diagnostics.json').read_text(encoding='utf-8'))
row=[r for r in d['rows'] if r['v4_outcome']=='NO_LEGAL_WINDOW_UNDER_CURRENT_RULES'][0]
print('G1 keys:', sorted(row['G1'].keys()))
print(json.dumps(row['G1'], ensure_ascii=False)[:2500])
