
import json
from pathlib import Path
d=json.loads(Path(r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D/outputs/overnight_3d_continuation/comparison/neutrality_v8_code.json').read_text(encoding='utf-8'))
for row in d['rows']:
    print('---', row['new_group'], 'vs', row['old_group'], 'status', row['new_status'], row['old_status'])
    for k,v in row.items():
        if k.startswith('same_') and v is not True:
            print('   DIFF', k)
    for k in ('step_trace_identical','near_distance_sets_identical','final_routes_identical','identical_all_tracked_fields'):
        print('   ', k, row.get(k))
