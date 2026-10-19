import json
from collections import Counter
from pathlib import Path

ROOT = Path('.')
payload = json.loads((ROOT / 'outputs/four_side_1024_d56_optimized/routes.json').read_text(encoding='utf-8'))
stats = payload['statistics']
print('=== final statistics ===')
for key in ('success_count', 'failed_count', 'success_rate', 'mean_length_mm',
            'max_length_mm', 'total_length_mm', 'candidate_evaluations',
            'total_runtime_seconds'):
    print(f'{key}: {stats.get(key)}')
print('by_pair:', json.dumps(stats['by_pair'], ensure_ascii=False))
print('by_relation:', json.dumps(stats['by_relation'], ensure_ascii=False))
print('failure reasons:', json.dumps(stats['failure_reason_counts'], ensure_ascii=False))
print('rejection totals:', json.dumps(stats['failed_candidate_rejection_counts'], ensure_ascii=False))
routes = payload['routes']
failed = [r for r in routes if r['status'] != 'routed']
print('failed ids by pair:', json.dumps(dict(Counter(r['pair'] for r in failed)), ensure_ascii=False))
fams = Counter()
for r in routes:
    if r['status'] == 'routed':
        fams[r['candidate']['family']] += 1
print('candidate families used:', dict(fams))
lens = [r['length_mm'] for r in routes if r['status'] == 'routed']
bends = [r['bend_count'] for r in routes if r['status'] == 'routed']
print('length min/mean/max: %.2f / %.2f / %.2f' % (min(lens), sum(lens) / len(lens), max(lens)))
print('bends mean %.2f  count dist %s' % (sum(bends) / len(bends), dict(Counter(bends))))
# failed route detail by side pair
by_side_pair = Counter((r['source_side'] + '>' + r['target_side']) for r in failed)
print('failed by directed side pair:', dict(by_side_pair))
# reason breakdown of failed rows
print('failed row reasons:', dict(Counter(r.get('reason') for r in failed)))
