
import json
from pathlib import Path
c=Path(r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D/outputs/overnight_3d_continuation/comparison')
p3=json.loads((c/'p3_family_and_target_limit.json').read_text(encoding='utf-8'))
print('=== P3 R-mode 2880 main ===')
for r in p3['rows']:
    if r['status']!='PRESENT' or r['mode']!='R' or r['budget']!=2880 or r.get('challenge'): continue
    print("  %-10s T%-5s evals=%5d used=%6.1f%% stop=%-32s pairs=%6d moves=%4d len=%7.2f ref=%s" % (
        r['arm'], r.get('max_targets'), r['candidate_evaluations'], r['budget_used_percent'],
        r['stop_reason'], r['final_collision_pairs'], r['accepted_moves'], r['stage_length_delta_mm'],
        'yes' if r.get('reused_reference') else 'no'))
print('=== P3 A_FAMILY T2000 all cells ===')
for r in p3['rows']:
    if r['status']=='PRESENT' and r['arm']=='A_FAMILY' and (r.get('max_targets') or 200)==2000:
        print("  %s%s %5d evals=%5d stop=%-32s pairs=%6d moves=%4d" % (
            r['mode'], 'C' if r.get('challenge') else ' ', r['budget'],
            r['candidate_evaluations'], r['stop_reason'], r['final_collision_pairs'],
            r['accepted_moves']))
p4=json.loads((c/'p4_length_cap.json').read_text(encoding='utf-8'))
print('=== P4 capped main (N and R) ===')
for r in p4['capped']:
    if r['status']!='PRESENT' or r.get('challenge'): continue
    print("  %-10s cap=%5.1f %s pairs=%6d len=%7.2f caprej=%4d checks=%5d head=%7.2f ev=%5d mv=%4d stop=%s" % (
        r['arm'], r['cap_mm'], r['mode'], r['final_collision_pairs'], r['stage_length_delta_mm'],
        r.get('stage_length_cap_rejections') or 0, r.get('stage_length_cap_checks') or 0,
        r.get('stage_length_cap_headroom_mm') or 0, r['candidate_evaluations'], r['accepted_moves'],
        r['stop_reason']))
print('=== P4 uncapped references ===')
for r in p4['uncapped_references']:
    if r['status']!='PRESENT': continue
    print("  %-10s %s%s pairs=%6d len=%7.2f ev=%5d mv=%4d" % (
        r['arm'], r['mode'], 'C' if r.get('challenge') else ' ', r['final_collision_pairs'],
        r['stage_length_delta_mm'], r['candidate_evaluations'], r['accepted_moves']))
