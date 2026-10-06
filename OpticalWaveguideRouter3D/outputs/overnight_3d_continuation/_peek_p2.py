
import json,sys
from pathlib import Path
root=Path(r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D')
def load(base,round,group):
    p=base/round/group/'summary.json'
    return json.loads(p.read_text(encoding='utf-8'))['stats'] if p.is_file() else None
cur=root/'outputs/overnight_3d_continuation'
hist=root/'outputs/overnight_3d_ideas'
pairs=[('V8_G1_N720','V7_T0_N720'),('V8_G1_N1440','V7_T0_N1440'),('V8_G1_N2880','V7_T0_N2880'),
       ('V8_G1_NC2880','V7_T0_NC2880'),('V8_G1_R720','V7_T0_R720'),('V8_G1_R1440','V7_T0_R1440'),
       ('V8_G1_R2880','V7_T0_R2880'),('V8_G1_RC2880','V7_T0_RC2880')]
print(f"{'group':16s} {'G1_final':>9s} {'G0_final':>9s} {'d':>7s} {'G1_ev':>6s} {'G1_mv':>6s} {'pw_exec':>8s} {'pw_gen':>7s} {'pw_eval':>7s} {'G1_len':>8s} {'G0_len':>8s}")
for g1,g0 in pairs:
    a=load(cur,'v8',g1); b=load(hist,'v7',g0)
    if a is None: print(f"{g1:16s} (not finished)"); continue
    fa=a['final_collision_pairs']; fb=b['final_collision_pairs'] if b else None
    ex=a.get('executed_moves_by_window_kind') or {}
    print(f"{g1:16s} {fa:9d} {str(fb):>9s} {str(fa-fb if fb else None):>7s} {a['candidate_evaluations']:6d} {a['accepted_moves']:6d} "
          f"{str(ex.get('PATH_WINDOW_G1',0)):>8s} {str((a.get('generation_accounting') or {}).get('path_window_candidates')):>7s} "
          f"{str((a.get('evaluated_candidates_by_window_kind') or {}).get('PATH_WINDOW_G1')):>7s} {a['stage_length_delta_mm']:8.2f} {b['stage_length_delta_mm'] if b else 0:8.2f}")
