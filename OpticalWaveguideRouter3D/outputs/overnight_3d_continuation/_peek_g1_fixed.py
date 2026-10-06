
import json
from pathlib import Path
cur=Path(r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D/outputs/overnight_3d_continuation')
hist=Path(r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D/outputs/overnight_3d_ideas')
def stats(base,round,group,suffix=''):
    p=base/round/(group+suffix)/'summary.json'
    return json.loads(p.read_text(encoding='utf-8'))['stats'] if p.is_file() else None
def ledger(base,round,group,suffix=''):
    p=base/round/(group+suffix)/'ledger.json'
    return json.loads(p.read_text(encoding='utf-8')) if p.is_file() else None
print("%-16s %8s %8s %7s %6s %6s %8s %8s %8s" % ('group','G1_fixed','G0','delta','evals','moves','pw_exec','endpt','defer'))
for mode in ('N','R'):
    for budget,ch in ((720,''),(1440,''),(2880,''),(2880,'C')):
        g="V8_G1_%s%s%d"%(mode,ch,budget)
        g0="V7_T0_%s%s%d"%(mode,ch,budget)
        a=stats(cur,'v8',g,'_boundaryfix'); b=stats(hist,'v7',g0)
        if a is None:
            print("%-16s (running)"%g); continue
        L=ledger(cur,'v8',g,'_boundaryfix') or {}
        ex=(L.get('executed_moves_by_window_kind') or {})
        print("%-16s %8d %8s %7s %6d %6d %8s %8d %8d" % (
            g, a['final_collision_pairs'], b['final_collision_pairs'] if b else '-',
            (a['final_collision_pairs']-b['final_collision_pairs']) if b else '-',
            a['candidate_evaluations'], a['accepted_moves'], ex.get('PATH_WINDOW_G1',0),
            L.get('basic_rejection_reason_counts',{}).get('ENDPOINT_CHANGED',0),
            L.get('deferred_prefix_no_winner',0)))
