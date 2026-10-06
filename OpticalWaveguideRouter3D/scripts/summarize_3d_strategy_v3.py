"""Step 16 summarizer: cross-group analysis of the 512 v3 ablation products.

Read-only on the per-group folders written by run_3d_strategy_v3.py. Emits
cross_group_analysis.json with the required reporting fields: terminal
close-pair and unresolved counts, accepted edits / extra length / transitions,
formal target attempts vs distinct targets vs repeats, generation-cache hits and
skips, generated vs evaluated candidates and full neighbour checks, self-check
ambiguity and insufficient-space rejections, budget usage and stop reason, phase
timings, and the relations to the historical strategy-B terminal state and the
revised-C baseline.

Usage (project root):
    .venv\\Scripts\\python.exe -B scripts\\summarize_3d_strategy_v3.py PROJECT OUTDIR
"""
import sys, json
from pathlib import Path

PROJECT = Path(sys.argv[1]).resolve(); OUT = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(PROJECT))

GROUPS = ['A_baseline_original', 'B_generation_cache_only', 'C_window_slack_only', 'D_both_enabled']
HIST_B = PROJECT/'outputs/3d_strategy_v2/512_three_layer_abc'
REV2_C = PROJECT/'outputs/3d_strategy_v2_rev2/512_c_fixed'


def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))


def load_group(name):
    folder = OUT/name
    summary = read(folder/'summary.json')
    return dict(name=name, config=read(folder/'config.json'), stats=summary['stats'],
        ledger=read(folder/'ledger.json'), skips=read(folder/'generation_skips.json'),
        collision_sets=read(folder/'collision_sets.json'),
        routes={r['route_id']: r['geometry'] for r in read(folder/'final_routes.json')['routes']},
        decisions=read(folder/'decisions.json'),
        recheck=read(folder/'recheck.json'))


def main():
    groups = {name: load_group(name) for name in GROUPS}
    acceptance_outcomes = {name: [dict(step=s['step_index'], target=list(s['target_pair']),
        moved=s.get('moved_route_id'), status=s['status']) for s in g['decisions']] for name, g in groups.items()}
    moved_routes = {name: sorted(s['moved'] for s in outcomes if s['moved'] is not None)
        for name, outcomes in acceptance_outcomes.items()}

    def route_diff(a, b): return sorted(i for i in groups[a]['routes'] if groups[a]['routes'][i] != groups[b]['routes'][i])

    matrix = {f'{a}|{b}': route_diff(a, b) for i, a in enumerate(GROUPS) for b in GROUPS[i+1:]}

    hist_b = {r['route_id']: r['geometry'] for r in read(HIST_B/'final_routes_B.json')['routes']}
    hist_b_moves = [(tuple(s['target_pair']), s.get('moved_route_id'), s['status'])
        for s in read(HIST_B/'decisions_B.json')]
    hist_b_ledger = read(HIST_B/'ledger_B.json')
    this_b = groups['B_generation_cache_only']
    this_b_moves = [(tuple(s['target_pair']), s.get('moved_route_id'), s['status']) for s in this_b['decisions']]
    rev2 = read(REV2_C/'ledger_C_fixed.json')
    a_stats = groups['A_baseline_original']['stats']

    record = dict(
        scale=512,
        dataset='LEGACY_512_SMOOTHED_P0 (existing synthetic 512 input; no real 1024 data used)',
        metric='centerline close-pair count at 0.1 mm clearance; not loss, crosstalk or manufacturability',
        groups={name: dict(
            generation_failure_cache=g['config']['generation_failure_cache'],
            window_slack_mm=g['config']['window_slack_mm'],
            final_collision_pairs=g['stats']['final_collision_pairs'],
            final_unresolved_pairs=g['stats']['final_unresolved_pairs'],
            accepted_moves=g['stats']['accepted_moves'], first_elevations=g['stats']['first_elevations'],
            relocations=g['stats']['relocations'],
            final_extra_length_mm=g['stats']['final_extra_length_mm'],
            step_length_delta_total_mm=g['stats']['step_length_delta_total_mm'],
            final_transition_count=g['stats']['final_transition_count'],
            target_attempts=g['stats']['target_attempts'], unique_targets=g['stats']['unique_targets'],
            repeat_attempts=g['stats']['repeat_attempts'], repeated_targets=g['stats']['repeated_targets'],
            generation_cache_enabled=g['stats']['generation_cache_enabled'],
            generation_cache_records=g['stats']['generation_cache_records'],
            generation_cache_zero_candidate_records=g['stats']['generation_cache_zero_candidate_records'],
            generation_skip_events=g['stats']['generation_skip_events'],
            generation_skipped_target_count=g['stats']['generation_skipped_target_count'],
            generated_candidates=g['stats']['generated_candidates'],
            candidate_evaluations=g['stats']['candidate_evaluations'],
            candidate_budget=g['stats']['candidate_budget'],
            full_neighbor_checks=g['stats']['full_neighbor_checks'],
            zero_candidate_victim_attempts=g['stats']['zero_candidate_victim_attempts'],
            generation_failure_reasons=g['stats']['generation_failure_reasons'],
            self_rejection_reasons=g['stats']['self_rejection_reasons'],
            full_rejection_reasons=g['stats']['full_rejection_reasons'],
            no_acceptable_move_steps=g['stats']['no_acceptable_move_steps'],
            budget_used_percent=g['stats']['budget_used_percent'], stop_reason=g['stats']['stop_reason'],
            timings=g['stats']['timings'],
            recheck_verdict=g['recheck']['verdict'], recheck_checks=g['recheck']['checks'],
            recheck_seconds=g['recheck']['recheck_seconds'],
            moved_route_ids=moved_routes[name]) for name, g in groups.items()},
        acceptance_outcomes=acceptance_outcomes,
        terminal_route_differences=matrix,
        skipped_pairs_detail={name: g['skips'] for name, g in groups.items() if g['skips']},
        relations=dict(
            group_A_matches_rev2_C=dict(
                final_collision_pairs=a_stats['final_collision_pairs'] == rev2['final_collision_pair_count'],
                accepted_moves=a_stats['accepted_moves'] == rev2['accepted_moves'],
                candidate_evaluations=a_stats['candidate_evaluations'] == rev2['candidate_evaluations'],
                decisions_sha256_identical=read(OUT/'A_baseline_original'/'previous_revision_strict_check.json')[
                    'decisions_identical'],
                terminal_routes_identical=read(OUT/'A_baseline_original'/'previous_revision_strict_check.json')[
                    'terminal_routes_identical']),
            group_B_equals_historical_strategy_B=dict(
                step_sequence_identical=this_b_moves == hist_b_moves,
                terminal_routes_identical=all(hist_b[i] == this_b['routes'][i] for i in hist_b),
                ledger_fields=dict(
                    final_collision_pairs=[this_b['ledger']['final_collision_pair_count'],
                        hist_b_ledger['final_collision_pair_count']],
                    accepted_moves=[this_b['ledger']['accepted_moves'], hist_b_ledger['accepted_moves']],
                    candidate_evaluations=[this_b['ledger']['candidate_evaluations'],
                        hist_b_ledger['candidate_evaluations']],
                    final_extra_length_mm=[this_b['ledger']['final_extra_length_mm'],
                        hist_b_ledger['final_extra_length_mm']]),
                interpretation=('on this 512 input the structural cache removes the two repeated zero-candidate '
                    'targets, and with zero relocation acceptances the C path then follows the same trajectory as '
                    'the historical strategy B; this is a mechanism result, not a target that was tuned for')),
            group_B_not_adjacent_to_prev_AB=('the historical 512 B terminal (43,750) and the historical revised-C '
                'terminal (44,274) must not be described as tied; they are different strategies, and this round '
                'reproduces both separately (A=revised C, B=historical B trajectory).')))

    note = ('A: baseline original. B: structural generation cache only. C: window slack only. D: both. '
        'Group letters are this round\'s feature ablation, not the historical strategy letters.')
    record['note'] = note
    target = OUT/'cross_group_analysis.json'
    target.write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(f'wrote {target}')
    for name in GROUPS:
        g = record['groups'][name]
        print(name, 'final', g['final_collision_pairs'], 'accepted', g['accepted_moves'],
            'attempts', g['target_attempts'], 'repeats', g['repeat_attempts'],
            'skips', g['generation_skip_events'], 'evals', g['candidate_evaluations'],
            'stop', g['stop_reason'])
    print('A == revised C:', record['relations']['group_A_matches_rev2_C'])
    print('B == historical strategy B:', record['relations']['group_B_equals_historical_strategy_B']['step_sequence_identical'],
        record['relations']['group_B_equals_historical_strategy_B']['terminal_routes_identical'])


if __name__ == '__main__':
    main()
