
import json
from pathlib import Path
d=json.loads(Path(r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D/outputs/overnight_3d_continuation/comparison/pe_multi_anchor_limit.json').read_text(encoding='utf-8'))
print('%-6s %-5s %-4s %-6s %8s %10s %-30s %8s %6s' % ('arm','limit','mode','budget','evals','used%','stop','pairs','moves'))
for r in d['rows']:
    if r['status']!='PRESENT': continue
    print('%-6s %-5d %-4s %-6d %8d %10.1f %-30s %8d %6d' % (r['arm'], r['max_targets'], r['mode'],
          r['budget'] + (2880 if r.get('challenge') else 0), r['candidate_evaluations'],
          r['budget_used_percent'], r['stop_reason'], r['final_collision_pairs'], r['accepted_moves']))
