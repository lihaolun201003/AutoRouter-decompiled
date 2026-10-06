"""Analysis of the Step 16 slack relocation diagnostic.

Read-only post-processing of outputs/3d_strategy_v3/512_relocation_slack_diagnostic
plus the Step 15 diagnostic it repeats. Produces:

* movement-class statistics for the OLD and NEW D/E runs under one counting rule
  (attempts, generated, basic evaluations, basic passes, full checks, full
  passes, accepted edits, failure reasons);
* per-target outcome comparison over the 20 fixed targets;
* a per-candidate correspondence for the recorded SELF_AMBIGUOUS_CLEARANCE rows.
  ALL movement classes (208 rows) and RELOCATION only (70 rows) are reported as
  two explicitly separate scopes; a row is claimed MATCHED only when exactly one
  candidate satisfies the window rule, several candidates are recorded as
  AMBIGUOUS_MULTIPLE_MATCHES instead of silently taking the nearest one, and
  unmatched rows are listed by reason and never claimed as resolved;
* window shifts in both the dimensionless parameter (start_shift_param, the same
  quantity the generator uses) and millimetres (start_shift_mm = parameter
  difference x that primitive's length);
* per-target evaluations counted as after-minus-before (never the cumulative
  candidate_evaluations_after) and cross-checked against the target's recorded
  candidate rows, with the per-mode sums compared to 324 (D) and 342 (E);
* a validation block covering the unit conversion, the movement-class filter,
  the target-level counts, the match uniqueness and the accepted-move bookkeeping;
* the accepted relocation record with the before/after geometry of the moved
  route (for the report figures).

Usage (project root):
    .venv\Scripts\python.exe -B scripts\analyze_relocation_slack_diagnostic.py PROJECT OUTDIR
"""
import sys, json, csv
from collections import Counter
from pathlib import Path

PROJECT = Path(sys.argv[1]).resolve(); OUT = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(PROJECT))

from src.models import Layer, Point3D
from src.geometry_3d import lift_smoothed_route_to_layer, CosineTransition3D
from src.multi_attribution import deserialize_plot
from src.fixed_1024_routing import deserialize_route3d, serialize_route3d
from src.strategy_v2_3d import SKIPPED_ELEVATED_STATUSES

OLD = PROJECT/'outputs/3d_strategy_v2_rev2/512_de_diagnostic'
START = PROJECT/'outputs/3d_strategy_v2/512_three_layer_abc/final_routes_B.json'
SLACK = json.loads((OUT/'config.json').read_text(encoding='utf-8'))['window_slack_mm']


def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))


def planar_routes():
    plot = read(PROJECT/'outputs/step_8_5_legacy_512_plot_geometry.json')
    return {r['id']: lift_smoothed_route_to_layer(deserialize_plot(r), Layer(0, 0)) for r in plot['routes']}


def movement_stats(steps):
    out = {}
    for movement in ('FIRST_ELEVATION', 'RELOCATION'):
        counts = {k: 0 for k in ('victim_attempts_total', 'victim_attempts_with_generation',
            'victim_attempts_skipped_no_generation', 'generated_candidates', 'basic_evaluations',
            'basic_passed', 'full_acceptance_checks', 'full_acceptance_passed', 'accepted_edits')}
        basic_reasons = Counter(); basic_reason_rows = Counter()
        full_reasons = Counter(); full_reason_rows = Counter(); generation_failures = Counter()
        for step in steps:
            for va in step['victim_attempts']:
                if va.get('movement') != movement: continue
                counts['victim_attempts_total'] += 1
                if va.get('status') in SKIPPED_ELEVATED_STATUSES:
                    counts['victim_attempts_skipped_no_generation'] += 1; continue
                counts['victim_attempts_with_generation'] += 1
                counts['generated_candidates'] += va.get('generated_count', 0)
                if va.get('generated_count', 0) == 0:
                    generation_failures[str(va.get('generation_failure'))] += 1
                if va.get('status') == 'SELECTED': counts['accepted_edits'] += 1
                for row in va['candidates']:
                    counts['basic_evaluations'] += 1
                    if row['basic_status'] == 'ACCEPTED_TARGET_PAIR_ONLY':
                        counts['basic_passed'] += 1
                    else:
                        for reason in (row.get('basic_reasons') or []): basic_reasons[reason] += 1
                        for reason in set(row.get('basic_reasons') or []): basic_reason_rows[reason] += 1
                    if row.get('full_reasons') is not None:
                        counts['full_acceptance_checks'] += 1
                        if row['status'] == 'ACCEPTED_FULL': counts['full_acceptance_passed'] += 1
                        else:
                            for reason in row['full_reasons']: full_reasons[reason] += 1
                            for reason in set(row['full_reasons']): full_reason_rows[reason] += 1
        out[movement] = dict(counts,
            basic_rejected=counts['basic_evaluations']-counts['basic_passed'],
            generation_failures=dict(generation_failures),
            basic_rejection_reason_occurrences=dict(basic_reasons),
            basic_rejection_candidates_with_reason=dict(basic_reason_rows),
            full_rejection_reason_occurrences=dict(full_reasons),
            full_rejection_candidates_with_reason=dict(full_reason_rows))
    return out


def step_target_status(steps):
    """Per-target record. evaluations is the number of basic evaluations spent
    INSIDE this target only (candidate_evaluations_after - candidate_evaluations_before),
    never the cumulative counter, and is cross-checked against the number of
    candidate rows actually recorded for the target."""
    out = {}
    for s in steps:
        pair = tuple(s['target_pair'])
        before = s.get('candidate_evaluations_before', 0)
        after = s.get('candidate_evaluations_after', before)
        rows = sum(len(va['candidates']) for va in s['victim_attempts'])
        out[pair] = dict(step=s['step_index'], status=s['status'],
            moved=s.get('moved_route_id'), movement=s.get('movement'),
            evaluations_after_cumulative=after, evaluations_before_cumulative=before,
            evaluations=after - before, recorded_candidate_rows=rows,
            evaluations_match_recorded_rows=(after - before) == rows)
    return out


def correspondence(old_decisions, new_decisions, planar, movement_filter=None):
    def index(decisions):
        tasks = {}
        for step in decisions:
            target = tuple(step['target_pair'])
            for va in step['victim_attempts']:
                key = (target, va['route_id'])
                entry = tasks.setdefault(key, dict(target=target, moved=va['route_id'],
                    movement=va.get('movement'), generated_count=va.get('generated_count'),
                    generation_failure=va.get('generation_failure'), rows=[]))
                for row in va['candidates']:
                    entry['rows'].append(dict(candidate_index=row['candidate_index'],
                        layer=row['target_layer_id'], rise_window=tuple(row['rise_window']),
                        fall_window=tuple(row['fall_window']), basic_status=row['basic_status'],
                        basic_reasons=row.get('basic_reasons') or [], status=row.get('status'),
                        full_reasons=row.get('full_reasons')))
        return tasks
    old_tasks, new_tasks = index(old_decisions), index(new_decisions)
    targets = []
    for key, task in sorted(old_tasks.items()):
        if movement_filter and task['movement'] != movement_filter: continue
        for row in task['rows']:
            if 'SELF_AMBIGUOUS_CLEARANCE' not in row['basic_reasons']: continue
            targets.append((key, task, row))
    records = []; transitions = Counter(); unmatched = Counter()
    for (target, moved), task, row in targets:
        entry = dict(target=list(target), moved=moved, movement=task['movement'],
            candidate_index=row['candidate_index'], layer=row['layer'],
            old_basic_status=row['basic_status'],
            old_rise_window=list(row['rise_window']), old_fall_window=list(row['fall_window']))
        new_task = new_tasks.get((target, moved))
        if new_task is None:
            entry['match'] = 'TASK_NOT_REACHED_IN_NEW_RUN'
            entry['match_reason'] = ('the target was no longer colliding when its turn came in the new run, '
                'so this generation task ran only in the old run; it is NOT counted as resolved')
            unmatched['TASK_NOT_REACHED_IN_NEW_RUN'] += 1; records.append(entry); continue
        ri, ru, rv = row['rise_window']; fi, fu, fv = row['fall_window']
        rise_length = planar[moved].primitives[ri].length()
        fall_length = planar[moved].primitives[fi].length()
        dr = 2*SLACK/rise_length+1e-15
        df = 2*SLACK/fall_length+1e-15
        hits = []
        for cand in new_task['rows']:
            cri, cru, crv = cand['rise_window']; cfi, cfu, cfv = cand['fall_window']
            if cand['layer'] != row['layer'] or cri != ri or cfi != fi: continue
            if abs((crv-cru)-(rv-ru)) > 1e-12 or abs((cfv-cfu)-(fv-fu)) > 1e-12: continue
            gap_r, gap_f = abs(cru-ru), abs(cfu-fu)
            if gap_r <= dr and gap_f <= df:
                hits.append((cand, gap_r, gap_f))
        # Uniqueness is asserted, not assumed: more than one admissible window is
        # recorded as an ambiguous row and is NOT counted as a correspondence.
        if len(hits) > 1:
            entry.update(match='AMBIGUOUS_MULTIPLE_MATCHES', match_count=len(hits),
                match_reason='%d candidates satisfy the window rule; no unique correspondence is claimed'
                             % len(hits))
            unmatched['AMBIGUOUS_MULTIPLE_MATCHES'] += 1; records.append(entry); continue
        if not hits:
            entry['match'] = 'NO_CORRESPONDING_WINDOW_IN_NEW_RUN'
            unmatched['NO_CORRESPONDING_WINDOW_IN_NEW_RUN'] += 1; records.append(entry); continue
        cand, gap_r, gap_f = hits[0]
        entry.update(match='MATCHED', match_count=1, new_candidate_index=cand['candidate_index'],
            new_rise_window=list(cand['rise_window']), new_fall_window=list(cand['fall_window']),
            start_shift_param=[gap_r, gap_f],
            start_shift_mm=[gap_r*rise_length, gap_f*fall_length],
            shift_conversion=dict(rise_primitive_length_mm=rise_length,
                fall_primitive_length_mm=fall_length,
                note='start_shift_mm = start_shift_param x the length of that primitive'),
            new_basic_status=cand['basic_status'],
            new_basic_reasons=cand['basic_reasons'], new_full_status=cand['status'],
            new_full_reasons=cand['full_reasons'])
        transitions[f"{row['basic_status']} -> {cand['basic_status']}"] += 1
        records.append(entry)
    matched = sum(1 for e in records if e.get('match') == 'MATCHED')
    full_pass = sum(1 for e in records if e.get('match') == 'MATCHED'
                    and e.get('new_full_status') == 'ACCEPTED_FULL')
    full_rej = sum(1 for e in records if e.get('match') == 'MATCHED'
                   and e.get('new_full_status') == 'REJECTED_FULL')
    full_rej_reasons = Counter(r for e in records if e.get('match') == 'MATCHED'
                               and e.get('new_full_status') == 'REJECTED_FULL'
                               for r in (e.get('new_full_reasons') or []))
    return dict(scope=('RELOCATION candidates only (70 of the 208 recorded rows)'
                       if movement_filter == 'RELOCATION'
                       else 'ALL movement classes (208 recorded rows: relocation + first elevation)'),
        movement_filter=movement_filter or 'ALL',
        movement_classes_included=(['RELOCATION'] if movement_filter == 'RELOCATION'
                                   else ['FIRST_ELEVATION', 'RELOCATION']),
        match_rule='exact (target, victim, layer, rise primitive, fall primitive, window width); '
                   'start shift <= 2*slack/length; MATCHED requires exactly one admissible candidate',
        old_self_ambiguous_rows=len(targets),
        matched=matched,
        unmatched=dict(unmatched),
        ambiguous_multiple_matches=unmatched.get('AMBIGUOUS_MULTIPLE_MATCHES', 0),
        old_to_new_basic_status=dict(transitions),
        matched_to_basic_pass=transitions.get('REJECTED -> ACCEPTED_TARGET_PAIR_ONLY', 0),
        matched_still_rejected=sum(v for k, v in transitions.items() if k.endswith('-> REJECTED')),
        matched_to_full_acceptance=full_pass,
        matched_full_rejected=full_rej,
        matched_full_reject_reasons=dict(full_rej_reasons),
        matched_is_candidate_count_not_accepts=(
            '%d matched rows PASSED the basic evaluation and %d of them also passed the full neighbour '
            'acceptance (%d were rejected there); these are candidate counts. Passing acceptance is not '
            'the same as being executed: a step executes only its selected winner.'
            % (transitions.get('REJECTED -> ACCEPTED_TARGET_PAIR_ONLY', 0), full_pass, full_rej)),
        records=records,
        note='The overall drop in ambiguous counts is not used as evidence. Only rows with exactly one '
             'admissible candidate in the new run are claimed as MATCHED; rows with several admissible '
             'candidates are reported as AMBIGUOUS_MULTIPLE_MATCHES and are never forced into a match.')


def main():
    planar = planar_routes()
    start = {row['route_id']: deserialize_route3d(row['geometry'])
        for row in read(START)['routes']}
    decisions = {('old', mode): read(OLD/f'decisions_{mode}.json') for mode in ('D', 'E')}
    decisions.update({('new', mode): read(OUT/f'decisions_{mode}.json') for mode in ('D', 'E')})
    ledgers = {('old', mode): read(OLD/f'ledger_{mode}.json') for mode in ('D', 'E')}
    ledgers.update({('new', mode): read(OUT/f'ledger_{mode}.json') for mode in ('D', 'E')})
    target_sets = {key: step_target_status(decisions[key]) for key in decisions}
    old_list = read(OLD/'target_list.json')['targets']
    status_of = {}
    for key, mapping in target_sets.items():
        for pair, info in mapping.items(): status_of[(key, pair)] = info
    rows = []
    for index, pair in enumerate(old_list):
        pair = tuple(pair)
        row = dict(target=list(pair), target_index=index + 1,
            both_elevated=index < 10)
        for key, label in ((('old', 'D'), 'old_D'), (('new', 'D'), 'new_D'),
                           (('old', 'E'), 'old_E'), (('new', 'E'), 'new_E')):
            info = status_of.get((key, pair))
            row[label] = info['status'] if info else 'TARGET_NOT_REACHED'
            row[label + '_evaluations'] = info['evaluations'] if info else 0
            row[label + '_moved'] = info['moved'] if info else None
        rows.append(row)
    stats = {f'{era}_{mode}': movement_stats(decisions[(era, mode)]) for era in ('old', 'new') for mode in ('D', 'E')}
    corr_reloc = correspondence(decisions[('old', 'E')], decisions[('new', 'E')], planar, 'RELOCATION')
    corr_all = correspondence(decisions[('old', 'E')], decisions[('new', 'E')], planar, None)
    accepted = []
    for mode in ('D', 'E'):
        for step in decisions[('new', mode)]:
            if step['status'] in ('ELEVATED', 'RELOCATED'):
                route = step['moved_route_id']
                accepted.append(dict(mode=mode, step_index=step['step_index'],
                    target_pair=list(step['target_pair']), route_id=route, movement=step['movement'],
                    target_layer_id=step['target_layer_id'], rise_window=list(step['rise_window']),
                    fall_window=list(step['fall_window']),
                    step_length_delta_mm=step['step_length_delta_mm'],
                    route_length_before_mm=step['route_length_before_mm'],
                    route_length_after_mm=step['route_length_after_mm'],
                    extra_length_vs_planar_mm=step['extra_length_mm_vs_planar'],
                    old_collisions_removed=step['old_collisions_removed'],
                    new_collisions_created=step['new_collisions_created'],
                    net_collision_reduction=step['net_collision_reduction'],
                    global_pairs_before=step['global_collision_pairs_before'],
                    global_pairs_after=step['global_collision_pairs_after'],
                    before_was_start_state=abs(step['route_length_before_mm']-start[route].total_length())<1e-9))
    relocation = [a for a in accepted if a['movement'] == 'RELOCATION']
    before_after = None
    if relocation:
        entry = relocation[0]
        terminal = {row['route_id']: deserialize_route3d(row['geometry'])
            for row in read(OUT/'final_routes_E.json')['routes']}
        before_after = dict(entry=entry, route_id=entry['route_id'],
            before=serialize_route3d(start[entry['route_id']]),
            after=serialize_route3d(terminal[entry['route_id']]),
            planar=serialize_route3d(planar[entry['route_id']]),
            before_transition_count=sum(isinstance(p, CosineTransition3D)
                for p in start[entry['route_id']].primitives),
            after_transition_count=sum(isinstance(p, CosineTransition3D)
                for p in terminal[entry['route_id']].primitives),
            before_length_mm=start[entry['route_id']].total_length(),
            after_length_mm=terminal[entry['route_id']].total_length(),
            planar_length_mm=planar[entry['route_id']].total_length(),
            note='the replacement was rebuilt from the frozen planar z=0 route; the route was replaced, '
                 'not stacked, so the transition count stays 2')
    # ---------------------------------------------------------------- validations
    def conversion_check(corr):
        violations = []
        max_mm = 0.0; max_param = 0.0
        for e in corr['records']:
            if e.get('match') != 'MATCHED': continue
            lengths = (e['shift_conversion']['rise_primitive_length_mm'],
                       e['shift_conversion']['fall_primitive_length_mm'])
            for mm, param, length in zip(e['start_shift_mm'], e['start_shift_param'], lengths):
                if abs(mm - param*length) > 1e-15: violations.append(dict(record=e, mm=mm, param=param))
                max_mm = max(max_mm, abs(mm)); max_param = max(max_param, abs(param))
        return dict(checked_rows=corr['matched'], violations=len(violations),
            max_abs_shift_mm=max_mm, max_abs_shift_param=max_param,
            expected_bound_mm=2*SLACK,
            within_bound=max_mm <= 2*SLACK + 1e-12,
            rule='start_shift_mm = start_shift_param x the primitive length; the parameter shift is '
                 'bounded by 2*slack/length, so the millimetre shift is bounded by 2*slack')

    target_checks = {}
    for key, label in ((('new', 'D'), 'new_D'), (('new', 'E'), 'new_E')):
        infos = list(target_sets[key].values())
        total = sum(i['evaluations'] for i in infos)
        recorded = sum(i['recorded_candidate_rows'] for i in infos)
        ledger_total = ledgers[key]['candidate_evaluations']
        target_checks[label] = dict(
            sum_of_per_target_evaluations=total,
            sum_of_recorded_candidate_rows=recorded,
            ledger_candidate_evaluations=ledger_total,
            every_target_matches_its_rows=all(i['evaluations_match_recorded_rows'] for i in infos),
            expected_total={'new_D': 324, 'new_E': 342}[label],
            verdict='PASS' if (total == recorded == ledger_total
                and all(i['evaluations_match_recorded_rows'] for i in infos)) else 'FAIL')

    relocation_step = next(s for s in decisions[('new', 'E')] if s['status'] == 'RELOCATED')
    d_by_step = {s['step_index']: s for s in decisions[('new', 'D')]}
    e_by_step = {s['step_index']: s for s in decisions[('new', 'E')]}
    fewer_new_pairs = []
    for index, step_d in sorted(d_by_step.items()):
        step_e = e_by_step.get(index)
        if step_d['status'] != 'ELEVATED' or step_e is None or step_e['status'] != 'ELEVATED':
            continue
        saved = len(step_d['new_collisions_created']) - len(step_e['new_collisions_created'])
        if saved:
            fewer_new_pairs.append(dict(step_index=index, route_id=step_d['moved_route_id'],
                target_pair=list(step_d['target_pair']),
                new_collisions_created_in_D=len(step_d['new_collisions_created']),
                new_collisions_created_in_E=len(step_e['new_collisions_created']), pairs_saved=saved))
    final_difference = (ledgers[('new', 'D')]['final_collision_pair_count']
                        - ledgers[('new', 'E')]['final_collision_pair_count'])
    removed_directly = len(relocation_step['old_collisions_removed'])
    benefit = dict(
        final_pair_difference_D_minus_E=final_difference,
        relocation_removed_pairs_directly=removed_directly,
        first_elevations_with_one_fewer_new_pair=fewer_new_pairs,
        pairs_saved_by_those_first_elevations=sum(x['pairs_saved'] for x in fewer_new_pairs),
        decomposition_holds=(removed_directly + sum(x['pairs_saved'] for x in fewer_new_pairs)
                             == final_difference),
        explanation='the route-34 relocation directly removes %d pairs; the first elevations of routes %s '
                    'each create one fewer new pair (%d in total), which sums to the %d-pair difference'
                    % (removed_directly, ', '.join(str(x['route_id']) for x in fewer_new_pairs),
                       sum(x['pairs_saved'] for x in fewer_new_pairs), final_difference))
    step_delta = relocation_step['step_length_delta_mm']
    length_difference = (ledgers[('new', 'E')]['final_extra_length_vs_planar_mm']
                         - ledgers[('new', 'D')]['final_extra_length_vs_planar_mm'])
    length_consistency = dict(relocation_step_delta_mm=step_delta,
        final_extra_length_difference_mm=length_difference,
        agree_within_1e_9=abs(step_delta - length_difference) < 1e-9,
        note='the single relocation step and the terminal D/E extra-length difference are the same '
             'quantity: only route 34 changes length in E relative to D')

    accepted_edits = {mode: dict(accepted_moves=ledgers[('new', mode)]['accepted_moves'],
        first_elevations=ledgers[('new', mode)]['first_elevations'],
        relocations=ledgers[('new', mode)]['relocations']) for mode in ('D', 'E')}
    accepted_edits['total'] = sum(v['accepted_moves'] for k, v in accepted_edits.items() if k in ('D', 'E'))
    accepted_edits['note'] = ('executed edits are counted from the ledgers: D %d and E %d, %d in total. '
        'These are executed modifications, not the number of candidates that passed acceptance '
        '(%d matched rows passed the basic evaluation and %d of those passed full acceptance).'
        % (accepted_edits['D']['accepted_moves'], accepted_edits['E']['accepted_moves'],
           accepted_edits['total'], corr_all['matched_to_basic_pass'],
           corr_all['matched_to_full_acceptance']))

    validations = dict(
        unit_conversion_all=conversion_check(corr_all),
        unit_conversion_relocation=conversion_check(corr_reloc),
        movement_class_filter=dict(
            all_scope_rows=corr_all['old_self_ambiguous_rows'],
            all_scope_classes=corr_all['movement_classes_included'],
            relocation_scope_rows=corr_reloc['old_self_ambiguous_rows'],
            relocation_scope_classes=corr_reloc['movement_classes_included'],
            relocation_rows_inside_all_scope=sum(
                1 for e in corr_all['records'] if e['movement'] == 'RELOCATION'),
            expected_all=208, expected_relocation=70,
            verdict='PASS' if (corr_all['old_self_ambiguous_rows'] == 208
                and corr_reloc['old_self_ambiguous_rows'] == 70
                and sum(1 for e in corr_all['records'] if e['movement'] == 'RELOCATION') == 70) else 'FAIL'),
        match_uniqueness=dict(
            all_scope=dict(matched=corr_all['matched'],
                ambiguous_multiple=corr_all['ambiguous_multiple_matches'],
                unmatched=corr_all['unmatched']),
            relocation_scope=dict(matched=corr_reloc['matched'],
                ambiguous_multiple=corr_reloc['ambiguous_multiple_matches'],
                unmatched=corr_reloc['unmatched']),
            every_matched_has_exactly_one_match=all(
                e.get('match_count') == 1 for e in corr_all['records'] + corr_reloc['records']
                if e.get('match') == 'MATCHED'),
            note='a MATCHED row requires exactly one admissible candidate; several admissible '
                 'candidates are recorded as AMBIGUOUS_MULTIPLE_MATCHES and are not forced into a match'),
        per_target_evaluations=target_checks,
        accepted_edit_counts=dict(
            new_D=accepted_edits['D']['accepted_moves'], new_E=accepted_edits['E']['accepted_moves'],
            total=accepted_edits['total'],
            new_E_relocations=accepted_edits['E']['relocations'],
            new_E_first_elevations=accepted_edits['E']['first_elevations'],
            matched_basic_pass=corr_all['matched_to_basic_pass'],
            matched_full_pass=corr_all['matched_to_full_acceptance'],
            matched_full_rejected=corr_all['matched_full_rejected'],
            note='passing acceptance is not execution: only the selected winner of a step is executed'),
        benefit_decomposition=dict(
            decomposition_holds=benefit['decomposition_holds'],
            relocation_removed_equals_expected=removed_directly == 26,
            saved_by_first_elevations=sum(x['pairs_saved'] for x in fewer_new_pairs) == 3,
            final_difference_is_29=final_difference == 29),
        length_consistency=dict(agree_within_1e_9=length_consistency['agree_within_1e_9'],
            step_delta_mm=step_delta, difference_mm=length_difference))
    validations['verdict'] = ('PASS' if all(
        [validations['unit_conversion_all']['violations'] == 0
         and validations['unit_conversion_all']['within_bound'],
         validations['unit_conversion_relocation']['violations'] == 0
         and validations['unit_conversion_relocation']['within_bound'],
         validations['movement_class_filter']['verdict'] == 'PASS',
         validations['match_uniqueness']['every_matched_has_exactly_one_match'],
         all(v['verdict'] == 'PASS' for v in target_checks.values()),
         all(validations['benefit_decomposition'].values()),
         validations['length_consistency']['agree_within_1e_9']]) else 'FAIL')

    correspondence_file = dict(
        produced_by='scripts/analyze_relocation_slack_diagnostic.py',
        produced_note='derived statistics only: the raw decisions, final routes, collision sets, ledger, '
                      'recheck and code_version files of the experiment are untouched',
        window_slack_mm=SLACK, match_rule=corr_all['match_rule'],
        scopes=dict(ALL_MOVEMENT_CLASSES=corr_all, RELOCATION_ONLY=corr_reloc),
        scope_summary=dict(all_movement_classes_rows=corr_all['old_self_ambiguous_rows'],
            relocation_only_rows=corr_reloc['old_self_ambiguous_rows']),
        generated_from=dict(old_decisions='outputs/3d_strategy_v2_rev2/512_de_diagnostic/decisions_E.json',
            new_decisions='outputs/3d_strategy_v3/512_relocation_slack_diagnostic/decisions_E.json'),
        note='This file used to declare a relocation-only scope while containing all 208 movement-class '
             'rows; both scopes are now explicit. The window shift is given as start_shift_param (the '
             'dimensionless parameter difference the generator uses) and start_shift_mm '
             '(parameter difference x that primitive length).')
    (OUT/'candidate_correspondence.json').write_text(json.dumps(correspondence_file, indent=2), encoding='utf-8')

    summary_path = OUT/'summary.json'
    summary = read(summary_path)
    summary['candidate_correspondence'] = dict(
        refreshed_by='scripts/analyze_relocation_slack_diagnostic.py',
        file='candidate_correspondence.json',
        ALL_MOVEMENT_CLASSES={k: corr_all[k] for k in
            ('scope', 'old_self_ambiguous_rows', 'matched', 'unmatched', 'ambiguous_multiple_matches',
             'old_to_new_basic_status')},
        RELOCATION_ONLY={k: corr_reloc[k] for k in
            ('scope', 'old_self_ambiguous_rows', 'matched', 'unmatched', 'ambiguous_multiple_matches',
             'old_to_new_basic_status')})
    summary['per_target_evaluations'] = target_checks
    summary['validations'] = validations
    summary_path.write_text(json.dumps(summary, indent=2), encoding='utf-8')

    record = dict(window_slack_mm=SLACK,
        source=dict(old_diagnostic=str(OLD), new_diagnostic=str(OUT), start_state=str(START)),
        budget_ceiling=json.loads((OUT/'config.json').read_text(encoding='utf-8'))['candidate_budget_ceiling'],
        counting_rule='one candidate = one basic evaluate_elevation call, rejections included; a candidate '
                      'may hold several rejection reasons, so reason occurrences and candidates-with-reason '
                      'are reported separately and never summed into a candidate count',
        movement_stats=stats,
        target_outcomes=rows,
        target_outcome_columns_note='old_D/new_D/old_E/new_E give the step status; the *_evaluations columns '
            'are after-minus-before for that target only (never the cumulative counter) and equal the number '
            'of candidate rows recorded for that target',
        per_target_evaluations=target_checks,
        validations=validations,
        accepted_edit_counts=dict(accepted_edits,
            new_D=accepted_edits['D']['accepted_moves'], new_E=accepted_edits['E']['accepted_moves'],
            new_E_relocations=accepted_edits['E']['relocations'],
            new_E_first_elevations=accepted_edits['E']['first_elevations'],
            matched_basic_pass=corr_all['matched_to_basic_pass'],
            matched_full_pass=corr_all['matched_to_full_acceptance'],
            matched_full_rejected=corr_all['matched_full_rejected']),
        benefit_decomposition=benefit,
        length_consistency=length_consistency,
        targets_no_longer_colliding_new=dict(D=sum(1 for r in rows if r['new_D'] == 'TARGET_NO_LONGER_COLLIDING'),
            E=sum(1 for r in rows if r['new_E'] == 'TARGET_NO_LONGER_COLLIDING')),
        targets_no_longer_colliding_old=dict(D=sum(1 for r in rows if r['old_D'] == 'TARGET_NO_LONGER_COLLIDING'),
            E=sum(1 for r in rows if r['old_E'] == 'TARGET_NO_LONGER_COLLIDING')),
        correspondence_relocation_candidates=corr_reloc,
        correspondence_all_movement_classes=corr_all,
        correspondence_file_scope_note='correspondence_relocation_candidates covers the 70 relocation rows; '
            'correspondence_all_movement_classes covers all 208 rows; see candidate_correspondence.json',
        accepted_moves=accepted, relocation_accepted=relocation,
        accepted_relocation_before_after=before_after,
        ledger_comparison={f'{era}_{mode}': {k: ledgers[(era, mode)][k] for k in
            ('final_collision_pair_count', 'final_unresolved_pair_count', 'accepted_moves',
             'first_elevations', 'relocations', 'relocation_victim_attempts',
             'relocation_candidate_evaluations', 'candidate_evaluations', 'generated_candidates',
             'full_neighbor_checks', 'step_length_delta_total_mm', 'final_extra_length_vs_planar_mm',
             'runtime_seconds', 'stop_reason', 'window_slack_mm') if k in ledgers[(era, mode)]}
            for era in ('old', 'new') for mode in ('D', 'E')},
        limitation='one start state, one pre-declared 20-target list, one input and one slack value; '
                   'runtime is a single measurement and is not an efficiency conclusion; all numbers are '
                   '0.1 mm centerline close-pair counts, not loss, crosstalk or manufacturability')
    (OUT/'analysis.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    with (OUT/'target_outcomes.csv').open('w', newline='', encoding='utf-8-sig') as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); writer.writeheader()
        for row in rows: writer.writerow(row)
    def sha256(path):
        import hashlib; return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    manifest = {str(p.relative_to(OUT)): dict(sha256=sha256(p), bytes=p.stat().st_size)
        for p in sorted(OUT.iterdir())
        if p.is_file() and p.name not in ('manifest.json',) and p.suffix in ('.json', '.csv')}
    (OUT/'manifest.json').write_text(json.dumps(dict(
        files=manifest, count=len(manifest),
        note='complete artifact manifest; hashes recorded after the analysis step'), indent=2), encoding='utf-8')
    print(json.dumps(dict(
        slack=SLACK,
        new_D=record['ledger_comparison']['new_D'], new_E=record['ledger_comparison']['new_E'],
        relocation_accepted=len(relocation),
        correspondence_relocation={k: corr_reloc[k] for k in
            ('scope', 'old_self_ambiguous_rows', 'matched', 'unmatched', 'ambiguous_multiple_matches',
             'old_to_new_basic_status')},
        correspondence_all={k: corr_all[k] for k in
            ('scope', 'old_self_ambiguous_rows', 'matched', 'unmatched', 'ambiguous_multiple_matches',
             'old_to_new_basic_status')},
        validations=validations,
        accepted_edit_counts=accepted_edits,
        benefit_decomposition=benefit,
        length_consistency=length_consistency,
        targets_no_longer_colliding_new=record['targets_no_longer_colliding_new']), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
