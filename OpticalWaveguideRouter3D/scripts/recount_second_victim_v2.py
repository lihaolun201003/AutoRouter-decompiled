"""Recount second_victim_success from saved decisions (old vs corrected rule).

Old (wrong) rule: last victim attempt of the step has priority_index == 1.
Corrected rule: the victim attempt of the actually selected route has
priority_index == 1.

Read-only on the saved experiment data; writes a comparison JSON into the
revision output directory.

Usage (project root):
    .venv\\Scripts\\python.exe -B scripts\\recount_second_victim_v2.py PROJECT OUTDIR
"""
import json, sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
OUT = Path(sys.argv[2]).resolve()
SOURCE = ROOT/'outputs'/'3d_strategy_v2'
OUT.mkdir(parents=True, exist_ok=True)

records = []
for size, folder in ((512, '512_three_layer_abc'), (1024, '1024_three_layer_abc')):
    for strategy in ('A', 'B', 'C'):
        path = SOURCE/folder/f'decisions_{strategy}.json'
        steps = json.loads(path.read_text(encoding='utf-8'))
        moves = [s for s in steps if s['status'] in ('ELEVATED', 'RELOCATED')]
        old_count = sum(1 for s in moves if s['victim_attempts'][-1]['priority_index'] == 1)
        corrected = 0
        inconsistent = 0
        for s in moves:
            moved = s['moved_route_id']
            attempts = [va for va in s['victim_attempts'] if va['route_id'] == moved]
            if len(attempts) != 1:
                inconsistent += 1
                continue
            if attempts[0]['priority_index'] == 1:
                corrected += 1
        stored_old_field = sum(1 for s in moves if s.get('second_victim_success'))
        records.append(dict(
            scale=size, strategy=strategy, accepted_moves=len(moves),
            old_rule_last_attempt=old_count, corrected_rule_selected_attempt=corrected,
            stored_second_victim_success_field=stored_old_field,
            inconsistent_steps=inconsistent,
            source=str(path), source_note='historical run; not re-executed for this statistic'))
        print(f'{size} {strategy}: accepted={len(moves)} old={old_count} corrected={corrected} '
              f'stored_field={stored_old_field} inconsistent={inconsistent}')

summary = dict(rule_old='last victim attempt priority_index == 1 (WRONG)',
               rule_corrected='selected victim attempt priority_index == 1',
               source_directory=str(SOURCE),
               note='A/B not re-executed; counts recomputed from saved decisions only.',
               records=records)
(OUT/'second_victim_recount.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'written': str(OUT/'second_victim_recount.json')}, ensure_ascii=False))
