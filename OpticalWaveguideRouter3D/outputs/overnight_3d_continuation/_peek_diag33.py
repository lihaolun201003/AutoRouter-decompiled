
import json
from collections import Counter
from pathlib import Path
d=json.loads(Path(r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter3D/outputs/overnight_3d_continuation/diagnostics/v8_side_diagnostics.json').read_text(encoding='utf-8'))
rows=d['rows']
old=[r for r in rows if r['v4_outcome']=='NO_LEGAL_WINDOW_UNDER_CURRENT_RULES']
print('old no-window sides:',len(old))
reasons=Counter()
for r in old:
    g1=r['G1']; g0=r['G0']
    st=g1.get('generation_stats') or {}
    nli=st.get('no_legal_interval') or {}
    ldf=st.get('length_does_not_fit') or {}
    reasons[(bool(nli.get('rise')), bool(nli.get('fall')), st.get('rise_window_count'), st.get('fall_window_count'),
             g1.get('path_window_pairs_before_rejection'), g1.get('curvature_rejected'), g1.get('generated_candidates'),
             g0.get('generated_candidates'))]+=1
print('pattern (rise_empty, fall_empty, rise_windows, fall_windows, pairs_before_rej, curvature_rej, g1_cands, g0_cands): count')
for k,v in sorted(reasons.items(), key=lambda x:-x[1]):
    print('  ',k,v)
print()
print('first 8 sides detail:')
for r in old[:8]:
    st=r['G1'].get('generation_stats') or {}
    print(' side',r['moved_route_id'],'target',r['target_pair'],'v4',r['v4_outcome'],
          'anchors',st.get('anchor_count'),'first',st.get('first_crossing_offset_mm'),
          'last',st.get('last_crossing_offset_mm'),'total',st.get('planar_total_length_mm'),
          'legal',st.get('legal_interval_mm'),'nli',st.get('no_legal_interval'),
          'ldf',st.get('length_does_not_fit'),'risew',st.get('rise_window_count'),
          'fallw',st.get('fall_window_count'),'pairs',r['G1'].get('path_window_pairs_before_rejection'),
          'curvrej',r['G1'].get('curvature_rejected'))
