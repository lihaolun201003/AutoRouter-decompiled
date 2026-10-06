"""Aggregate the six v4 budget experiments and answer the eight experiment
questions from the saved artifacts only.

Usage (project root):
    .venv\\Scripts\\python.exe -B scripts\\summarize_3d_strategy_v4.py PROJECT OUTDIR
"""
import sys, json, csv
from collections import Counter
from pathlib import Path


def parse_args(argv):
    if len(argv) != 3: raise SystemExit(__doc__)
    return Path(argv[1]).resolve(), Path(argv[2]).resolve()


ROOT, OUT = parse_args(sys.argv)
GROUPS = ['N720', 'R720', 'N1440', 'R1440', 'N2880', 'R2880']
BUDGETS = [720, 1440, 2880]


def jsread(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def group_data():
    data = {}
    for name in GROUPS:
        folder = OUT/name
        if not (folder/'summary.json').is_file(): raise SystemExit(f'missing {folder}/summary.json')
        data[name] = dict(
            summary=jsread(folder/'summary.json'), stats=jsread(folder/'summary.json')['stats'],
            ledger=jsread(folder/'ledger.json'), curve=jsread(folder/'curve.json'),
            decisions=jsread(folder/'decisions.json'), recheck=jsread(folder/'recheck.json'),
            route_skips=jsread(folder/'route_skips.json'),
            generation_skips=jsread(folder/'generation_skips.json'),
            collision_sets=jsread(folder/'collision_sets.json'))
    return data


def marginal_blocks(curve, start_pairs, block):
    """Pairs removed inside each appended-evaluation block of `block` units."""
    rows = []
    previous = 0; previous_pairs = start_pairs
    for boundary in range(block, 10**9, block):
        reached = [r for r in curve if r['candidate_evaluations'] <= boundary]
        if not reached: break
        last = reached[-1]
        rows.append(dict(block_index=len(rows) + 1,
            evaluations_from=previous, evaluations_to=last['candidate_evaluations'],
            pairs_at_end=last['collision_pair_count'],
            pairs_removed=previous_pairs - last['collision_pair_count'],
            removed_cumulative=last['cumulative_removed'],
            created_cumulative=last['cumulative_created']))
        previous, previous_pairs = last['candidate_evaluations'], last['collision_pair_count']
        if last['candidate_evaluations'] < boundary: break
    return rows


def parse_pytest_log(path):
    import re
    text = Path(path).read_text(encoding='utf-8-sig', errors='replace')
    tail = [ln.strip() for ln in text.splitlines() if ln.strip()]
    summary = next((ln for ln in reversed(tail) if re.search(r'\d+ (passed|failed|error)', ln)),
        '未找到结果行')
    m = re.search(r'in ([\d.]+)s', summary)
    return dict(summary=re.sub(r'\s*in [\d.]+s.*$', '', summary),
        seconds=m.group(1) if m else '未知', path=str(path))


TEST_RUNS = [
    ('.venv\\Scripts\\python.exe -B -m pytest tests\\ -q', OUT/'pytest_full_v4.log'),
    ('..\\OpticalWaveguideRouter2D\\.venv\\Scripts\\python.exe -B -m pytest '
     'tests\\test_opt2d.py tests\\test_opt2d_step13.py tests\\test_opt2d_step13_fixes.py '
     'tests\\test_opt2d_step14.py -q', OUT/'pytest_opt2d_2d_env_v4.log'),
]


def write_test_summary():
    runs = []
    for command, path in TEST_RUNS:
        if not Path(path).is_file(): continue
        record = parse_pytest_log(path)
        runs.append(dict(command=command, summary=record['summary'], seconds=record['seconds'],
            log=str(path)))
    data = dict(runs=runs,
        note=('the 3D interpreter skips four test MODULES at module level (pytest.importorskip("scipy")); '
              'those four modules are executed separately with the 2D project interpreter'),
        generated_from=[str(p) for _, p in TEST_RUNS])
    (OUT/'3d_strategy_v4_test_summary.json').write_text(json.dumps(data, indent=2, ensure_ascii=False),
        encoding='utf-8')
    return data


def main():
    data = group_data()
    start = jsread(OUT/'start_state_check.json') if (OUT/'start_state_check.json').is_file() else None
    if start is None:
        candidates = sorted(OUT.glob('start_state_check*.json'))
        start = jsread(candidates[0])
    start_pairs = start['recomputed_collision_pair_count']
    comparison = []
    for name in GROUPS:
        s = data[name]['stats']
        ledger = data[name]['ledger']
        comparison.append(dict(group=name, mode=s['mode'], appended_candidate_budget=s['appended_candidate_budget'],
            final_collision_pairs=s['final_collision_pairs'],
            final_unresolved_pairs=s['final_unresolved_pairs'],
            pairs_removed_vs_start=start_pairs - s['final_collision_pairs'],
            accepted_moves=s['accepted_moves'], first_elevations=s['first_elevations'],
            relocations=s['relocations'],
            first_elevation_net_reduction=s['first_elevation_net_reduction'],
            relocation_net_reduction=s['relocation_net_reduction'],
            old_removed=s['total_old_collisions_removed'],
            new_created=s['total_new_collisions_created'],
            generated_candidates=s['generated_candidates'],
            candidate_evaluations=s['candidate_evaluations'],
            full_neighbor_checks=s['full_neighbor_checks'],
            full_acceptance_passes=s['full_acceptance_passes'],
            target_attempts=s['target_attempts'], stop_reason=s['stop_reason'],
            generation_skip_events=s['generation_skip_events'],
            no_movable_route_skip_events=s['no_movable_route_skip_events'],
            relocation_candidate_evaluations=s['relocation_candidate_evaluations'],
            final_elevated_route_count=s['final_elevated_route_count'],
            layer_route_counts=s['layer_route_counts'],
            stage_length_delta_mm=s['stage_length_delta_mm'],
            final_extra_length_vs_planar_mm=s['final_extra_length_vs_planar_mm'],
            step_length_delta_min_mm=s['step_length_delta_min_mm'],
            final_transition_count=s['final_transition_count'],
            runtime_seconds=s['timings']['runtime_seconds'],
            run_seconds_including_io=s['run_seconds_including_io'],
            recheck_verdict=data[name]['recheck']['verdict'],
            recheck_geometry_ok=all(v is True for k, v in data[name]['recheck']['geometry'].items()
                if k.endswith(('invariant', 'direction', 'pass', 'preserved', 'structure'))),
            initial_pair_state_distribution=s['initial_pair_state_distribution'],
            final_pair_state_distribution=s['final_pair_state_distribution'],
            basic_rejection_reason_counts=s['basic_rejection_reason_counts'],
            full_rejection_reason_counts=s['full_rejection_reason_counts'],
            generation_failure_reason_counts=s['generation_failure_reason_counts'],
            budget_checkpoints=s['budget_checkpoints'],
            zero_candidate_victim_attempts=ledger['zero_candidate_victim_attempts'],
            aborted_steps=ledger['aborted_steps'],
            aborted_steps_that_still_executed_a_move=ledger['aborted_steps_that_still_executed_a_move'],
            appended_candidate_budget_used_percent=ledger['appended_candidate_budget_used_percent'],
            already_elevated_victim_skips=ledger['already_elevated_victim_skips'],
            failed_no_candidates=ledger['failed_no_candidates'],
            failed_all_rejected=ledger['failed_all_rejected'],
            failed_no_winner=ledger['failed_no_winner'],
            failed_no_movable_route=ledger['failed_no_movable_route']))
    by_group = {row['group']: row for row in comparison}

    paired = []
    for budget in BUDGETS:
        n = by_group[f'N{budget}']; r = by_group[f'R{budget}']
        paired.append(dict(appended_candidate_budget=budget,
            n_final_pairs=n['final_collision_pairs'], r_final_pairs=r['final_collision_pairs'],
            n_pairs_removed=n['pairs_removed_vs_start'], r_pairs_removed=r['pairs_removed_vs_start'],
            difference_pairs=r['final_collision_pairs'] - n['final_collision_pairs'],
            n_first_elevations=n['first_elevations'], r_first_elevations=r['first_elevations'],
            n_relocations=n['relocations'], r_relocations=r['relocations'],
            n_evaluations=n['candidate_evaluations'], r_evaluations=r['candidate_evaluations'],
            same_actual_evaluations=n['candidate_evaluations'] == r['candidate_evaluations'],
            r_relocation_evaluations=r['relocation_candidate_evaluations'],
            n_extra_length_mm=n['stage_length_delta_mm'], r_extra_length_mm=r['stage_length_delta_mm'],
            verdict=('R_BETTER_BY_%d' % (n['final_collision_pairs'] - r['final_collision_pairs'])
                if r['final_collision_pairs'] < n['final_collision_pairs']
                else 'R_WORSE_BY_%d' % (r['final_collision_pairs'] - n['final_collision_pairs'])
                if r['final_collision_pairs'] > n['final_collision_pairs'] else 'IDENTICAL')))

    trends = []
    for mode in ('N', 'R'):
        previous_pairs = start_pairs; previous_budget = 0
        for budget in BUDGETS:
            row = by_group[f'{mode}{budget}']
            trends.append(dict(mode=mode, appended_candidate_budget=budget,
                final_collision_pairs=row['final_collision_pairs'],
                pairs_removed_from_start=previous_pairs - row['final_collision_pairs'],
                pairs_removed_in_this_step=previous_pairs - row['final_collision_pairs'],
                evaluations_added=row['candidate_evaluations'] - previous_budget,
                pairs_removed_per_720_evaluations=round(
                    720*(previous_pairs - row['final_collision_pairs'])
                    /max(1, row['candidate_evaluations'] - previous_budget), 2),
                old_removed=row['old_removed'], new_created=row['new_created'],
                first_elevations=row['first_elevations'], relocations=row['relocations'],
                stop_reason=row['stop_reason']))
            previous_pairs = row['final_collision_pairs']; previous_budget = row['candidate_evaluations']

    questions = {
        'Q1_more_budget_covers_more_unelevated_routes': dict(
            evidence={name: dict(final_elevated_route_count=by_group[name]['final_elevated_route_count'],
                first_elevations=by_group[name]['first_elevations'],
                both_unelevated_pairs=by_group[name]['final_pair_state_distribution']['both_routes_unelevated'],
                layer_route_counts=by_group[name]['layer_route_counts'])
                for name in GROUPS},
            note='coverage is reported as elevated route count, first elevations and the '
                 'both-unelevated residual pair count; nothing is inferred beyond the six runs'),
        'Q2_pairs_keep_falling_and_marginal_return': dict(trends=trends),
        'Q3_where_candidate_evaluations_are_spent': dict(
            per_group={name: dict(basic_rejection_reason_counts=by_group[name]['basic_rejection_reason_counts'],
                full_rejection_reason_counts=by_group[name]['full_rejection_reason_counts'],
                generation_failure_reason_counts=by_group[name]['generation_failure_reason_counts'],
                generated_candidates=by_group[name]['generated_candidates'],
                candidate_evaluations=by_group[name]['candidate_evaluations'],
                full_neighbor_checks=by_group[name]['full_neighbor_checks'],
                zero_candidate_victim_attempts=by_group[name]['zero_candidate_victim_attempts'])
                for name in GROUPS}),
        'Q4_did_R_generate_evaluate_and_accept_relocations': dict(
            per_group={name: dict(relocations=by_group[name]['relocations'],
                relocation_candidate_evaluations=by_group[name]['relocation_candidate_evaluations'],
                relocation_net_reduction=by_group[name]['relocation_net_reduction'],
                relocation_victim_attempts=None) for name in GROUPS},
            note='relocation_victim_attempts is filled from the ledgers below'),
        'Q5_is_R_better_than_N_at_the_same_budget': dict(paired=paired),
        'Q6_how_much_gain_comes_from_first_elevation_vs_relocation': dict(
            per_group={name: dict(first_elevation_net_reduction=by_group[name]['first_elevation_net_reduction'],
                relocation_net_reduction=by_group[name]['relocation_net_reduction'],
                first_elevations=by_group[name]['first_elevations'],
                relocations=by_group[name]['relocations']) for name in GROUPS}),
        'Q7_how_much_new_pairs_offset_the_removals': dict(
            per_group={name: dict(old_removed=by_group[name]['old_removed'],
                new_created=by_group[name]['new_created'],
                net=by_group[name]['old_removed'] - by_group[name]['new_created'],
                new_as_percent_of_removed=round(100*by_group[name]['new_created']
                    /max(1, by_group[name]['old_removed']), 3)) for name in GROUPS}),
        'Q8_final_residual_state_distribution_shift': dict(
            per_group={name: dict(initial=by_group[name]['initial_pair_state_distribution'],
                final=by_group[name]['final_pair_state_distribution'],
                change=dict(both_routes_unelevated=(
                    by_group[name]['final_pair_state_distribution']['both_routes_unelevated']
                    - by_group[name]['initial_pair_state_distribution']['both_routes_unelevated']),
                    single_route_elevated=(
                    by_group[name]['final_pair_state_distribution']['single_route_elevated']
                    - by_group[name]['initial_pair_state_distribution']['single_route_elevated']),
                    both_routes_elevated=(
                    by_group[name]['final_pair_state_distribution']['both_routes_elevated']
                    - by_group[name]['initial_pair_state_distribution']['both_routes_elevated'])))
                for name in GROUPS})}
    for name in GROUPS:
        ledger = data[name]['ledger']
        questions['Q4_did_R_generate_evaluate_and_accept_relocations']['per_group'][name][
            'relocation_victim_attempts'] = ledger['relocation_victim_attempts']
        questions['Q4_did_R_generate_evaluate_and_accept_relocations']['per_group'][name][
            'relocation_victims_selected'] = ledger['relocation_victims_selected']

    aggregate = dict(start_state=start, budgets=BUDGETS, groups=GROUPS,
        comparison=comparison, paired_n_vs_r=paired, trends=trends,
        marginal_blocks={name: marginal_blocks(data[name]['curve'], start_pairs, 720) for name in GROUPS},
        questions=questions,
        recheck={name: data[name]['recheck'] for name in GROUPS},
        recheck_length_ledger={name: data[name]['recheck']['length_ledger'] for name in GROUPS},
        budget_scope_note=('the budget of every group is appended to the common start state; the 720 '
            'candidate evaluations that produced that start state are not included'),
        relativity_note=('best-in-class marking is only meaningful between N and R at the SAME budget; '
            'different budgets are shown as a trend, not as a ranking'))
    (OUT/'summary_all_v4.json').write_text(json.dumps(aggregate, indent=2), encoding='utf-8')
    with (OUT/'comparison_v4.csv').open('w', newline='', encoding='utf-8-sig') as f:
        keys = list(comparison[0].keys())
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for row in comparison:
            writer.writerow({k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
                for k, v in row.items()})
    print(json.dumps(dict(
        final_pairs={row['group']: row['final_collision_pairs'] for row in comparison},
        removed={row['group']: row['pairs_removed_vs_start'] for row in comparison},
        moves={row['group']: dict(first=row['first_elevations'], reloc=row['relocations'],
            evals=row['candidate_evaluations'], stop=row['stop_reason']) for row in comparison},
        paired={p['appended_candidate_budget']: p['verdict'] for p in paired},
        recheck={row['group']: row['recheck_verdict'] for row in comparison}), indent=2))
    print('SUMMARY DONE')


if __name__ == '__main__':
    write_test_summary()
    main()
