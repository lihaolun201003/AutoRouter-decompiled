
import json,sys
from pathlib import Path
p=Path(r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D/outputs/overnight_3d_continuation/comparison/p5_serial_timing.json')
d=json.loads(p.read_text(encoding='utf-8'))
for row in d['rows']:
    print(row['arm'], row['sequence'], row['status'],
          'scan', row.get('initial_pair_scan_seconds'), 'engine', row.get('runtime_seconds'),
          'total', row.get('run_seconds_including_recheck'), 'io', row.get('recheck_and_io_seconds'),
          'evals', row.get('candidate_evaluations'), 'hits', row.get('decision_cache_hits'),
          'pairs', row.get('final_collision_pairs'), 'len', row.get('stage_length_delta_mm'),
          'moves', row.get('accepted_moves'), row.get('recheck_verdict'))
print('median engine', json.dumps(d['median_runtime_seconds']))
print('median total', json.dumps(d['median_run_seconds_including_recheck']))
print('median scan', json.dumps(d['median_scan_seconds']))
print('median assignment', json.dumps(d['median_assignment_seconds']))
print('consistency', json.dumps(d['consistency']))
