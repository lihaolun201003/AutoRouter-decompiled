
import json, os, sys, glob
root = sys.argv[1]
rows = []
for p in glob.glob(os.path.join(root, '**', 'summary.json'), recursive=True):
    rel = os.path.relpath(p, root)
    if 'aborted_arms' in rel: continue
    j = json.load(open(p, encoding='utf-8'))
    s = j.get('stats', {})
    sp = s.get('strategy_spec', {})
    t = s.get('timings', {})
    rows.append(dict(group=j.get('group'), round=j.get('round'), spec=s.get('strategy'),
        tp=sp.get('target_policy'), ep=sp.get('evaluation_policy'), mt=s.get('max_targets'),
        frr=sp.get('family_round_robin'), k=sp.get('k_per_target'),
        mode=s.get('mode'), budget=s.get('appended_candidate_budget'),
        final=s.get('final_collision_pairs'), evals=s.get('candidate_evaluations'),
        sec=round(t.get('runtime_seconds', 0) or t.get('total_seconds', 0) or 0, 1),
        stop=s.get('stop_reason'), moves=s.get('executed_moves'),
        reloc=s.get('relocations'),
        dl=round(s.get('stage_length_delta_mm') or 0, 2),
        unc=s.get('final_unresolved_pairs'),
        keys=','.join(sorted(t.keys()))[:60]))
rows.sort(key=lambda r: (str(r['spec']), str(r['mode']), r['budget'] or 0, str(r['round'])))
print(f"{'group':26s} {'spec':12s} {'tp':8s} {'ep':20s} {'mt':5s} {'frr':6s} {'m':2s} {'bud':5s} {'fin':5s} {'eval':5s} {'sec':7s} {'mov':4s} {'rel':4s} {'dL':8s} {'unc':4s} stop")
for r in rows:
    print(f"{str(r['group']):26s} {str(r['spec']):12s} {str(r['tp']):8s} {str(r['ep']):20s} {str(r['mt']):5s} {str(r['frr']):6s} {str(r['mode']):2s} {str(r['budget']):5s} {str(r['final']):5s} {str(r['evals']):5s} {str(r['sec']):7s} {str(r['moves']):4s} {str(r['reloc']):4s} {str(r['dl']):8s} {str(r['unc']):4s} {str(r['stop'])}")
print('TOTAL', len(rows))
r2880 = [r for r in rows if r['budget'] == 2880]
secs = sorted(x['sec'] for x in r2880)
print('R2880 sec: min', secs[0], 'median', secs[len(secs)//2], 'max', secs[-1], 'n', len(secs))
print('timing keys sample:', rows[0]['keys'])
