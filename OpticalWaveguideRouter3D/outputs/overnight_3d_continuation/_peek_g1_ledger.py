
import json,sys
from pathlib import Path
d=Path(r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D/outputs/overnight_3d_continuation/v8/V8_G1_N2880')
L=json.loads((d/'ledger.json').read_text(encoding='utf-8'))
for k in ('final_collision_pair_count','candidate_evaluations','accepted_moves','target_attempts','stop_reason',
          'generated_candidates','basic_rejection_reason_counts','full_rejection_reason_counts',
          'not_evaluated_candidates','not_evaluated_by_k_prefix','not_evaluated_by_budget',
          'failed_no_candidates','failed_all_rejected','failed_no_winner','deferred_prefix_no_winner',
          'candidates_by_window_kind','evaluated_candidates_by_window_kind',
          'full_accepted_candidates_by_window_kind','executed_moves_by_window_kind',
          'generation_accounting','final_path_window_transition_count','final_logical_ramp_count',
          'final_physical_fragment_count'):
    v=L.get(k)
    print(k,'=',json.dumps(v,ensure_ascii=False)[:600])
steps=json.loads((d/'decisions.json').read_text(encoding='utf-8'))
from collections import Counter
print('steps',len(steps))
print('step statuses',Counter(s['status'] for s in steps))
kinds=Counter()
offered=Counter()
for s in steps:
    for va in s['victim_attempts']:
        for e in va.get('candidates',[]):
            kinds[(e.get('window_kind'),e['status'],e.get('not_evaluated_reason'))]+=1
for k,v in sorted(kinds.items(), key=lambda x:-x[1])[:14]:
    print(' ',k,v)
