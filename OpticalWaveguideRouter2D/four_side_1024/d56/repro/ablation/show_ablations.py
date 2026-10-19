import json
from pathlib import Path
d = json.loads(Path('outputs/four_side_1024_d56_optimized/ablations.json').read_text(encoding='utf-8'))
for r in d['experiments']:
    br = r.get('by_relation') or {}
    op = (br.get('opposite') or {}).get('success')
    adj = (br.get('adjacent') or {}).get('success')
    print(f"{r['label']:>38s} {str(r['success']):>5} opp={op} adj={adj} "
          f"len={r.get('mean_length_mm')} x={r.get('crossing_count')} "
          f"policy={r.get('crossing_policy')}")
