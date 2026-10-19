"""Aggregate the instrumented replays into the numbers used by the diagnosis
report (Q1, Q5, Q7, Q8) and re-check sampled rule rejections (Q2, Q4).

Inputs (produced by probe_replay.py):
  data/replay/full_unlimited.json (+ _exact.csv, _samples.csv)
  data/replay/order_adjacent_only.json
  data/replay/order_opposite_only.json
  data/replay/order_opposite_first.json
  data/policy_search/policyC_full_unlimited.json
  outputs/four_side_1024_legacy_two_branch_v2/*  (deployed baseline)

Writes data/analysis.json, data/q1_replay_by_pair.json, data/q5_redundancy.json,
data/q8_spacing_dist.csv.
"""
from __future__ import annotations

import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

import d56_diag_common as C
import crossing_policy as P

DATA = C.DATA


def load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def read_exact_csv(path):
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    with path.open(encoding='utf-8') as f:
        for row in csv.DictReader(f):
            rows.append(dict(route_id=int(row['route_id']),
                             track_index=row['track_index'],
                             y=float(row['y']) if row['y'] not in ('', 'None') else None,
                             reason=row['reason'],
                             first_blocker=int(row['first_blocker']) if row['first_blocker'] not in ('', 'None') else None,
                             distance=float(row['distance']) if row['distance'] not in ('', 'None') else None,
                             n_blockers=int(row['n_blockers'])))
    return rows


def read_samples_csv(path):
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding='utf-8') as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Q1 / Q5: replay comparison per pair
# ---------------------------------------------------------------------------
def replay_stats(payload):
    rows = payload['route_rows']
    by_pair = defaultdict(lambda: Counter())
    for row in rows:
        p = by_pair[row['pair']]
        p['attempted'] += 1
        p['accepted'] += int(row['accepted'])
        p['scanned'] += row['scanned']
        p['order_fail'] += row['order_fail']
        p['nocross_fail'] += row['nocross_fail']
        p['bend_fail'] += row['bend_fail']
        p['validate_fail'] += row['validate_fail']
        p['exact'] += row['exact']
        p['exact_reject'] += row['exact_reject']
        p['route_count'] += 1
    out = {}
    for pair, c in by_pair.items():
        out[pair] = {k: c[k] for k in c}
        n = c['route_count']
        scanned = max(c['scanned'], 1)
        out[pair].update(
            mean_scanned_per_route=round(c['scanned'] / n, 1),
            mean_exact_per_route=round(c['exact'] / n, 1),
            scanned_to_exact_ratio=round(c['exact'] / scanned, 4),
            order_fail_fraction=round(c['order_fail'] / scanned, 4),
            nocross_fail_fraction=round(c['nocross_fail'] / scanned, 4),
            bend_fail_fraction=round(c['bend_fail'] / scanned, 4),
            validate_reached_fraction=round(c['exact'] / scanned, 4),
            exact_reject_fraction=round(c['exact_reject'] / max(c['exact'], 1), 4))
    return out


def first_blocker_table(rows):
    """Q1: which already-routed route blocks each failed candidate scan."""
    out = {}
    by_pair = defaultdict(Counter)
    for row in rows:
        if row['first_blocker'] is not None:
            by_pair[row['pair']][row['first_blocker']] += 1
    for pair, counter in by_pair.items():
        total = sum(counter.values())
        top = counter.most_common(6)
        out[pair] = dict(failed_routes_with_blocker=total,
                          top_blockers=[dict(blocker=int(b), count=c, share=round(c / total, 4))
                                        for b, c in top])
    return out


def blocker_share_gini(rows):
    """How concentrated the blocking is on a few routes (Q1)."""
    counter = Counter(row['first_blocker'] for row in rows if row['first_blocker'] is not None)
    values = sorted(counter.values(), reverse=True)
    total = sum(values)
    if not total:
        return dict(concentration=0., top1_share=0., top5_share=0.)
    cumulative = np.cumsum(values) / total
    return dict(blocker_count=len(values), top1_share=round(values[0] / total, 4),
                top5_share=round(sum(values[:5]) / total, 4),
                top10_share=round(sum(values[:10]) / total, 4),
                top20_share=round(sum(values[:20]) / total, 4))


# ---------------------------------------------------------------------------
# Q5: repeated / equivalent exact evaluations
# ---------------------------------------------------------------------------
def redundancy(exact_rows):
    """An exact evaluation is counted as 'repeated/equivalent' when the previous
    exact evaluation of the same route was rejected by the *same first blocker*
    (i.e. the scan keeps re-testing the same obstruction at a shifted track)."""
    by_route = defaultdict(list)
    for row in exact_rows:
        by_route[row['route_id']].append(row)
    repeated = 0
    total = 0
    runs = Counter()
    for rid, rows in by_route.items():
        previous = None
        run_length = 0
        for row in rows:
            total += 1
            if previous is not None and row['first_blocker'] == previous:
                repeated += 1
                run_length += 1
            else:
                if run_length:
                    runs[run_length] += 1
                run_length = 0
            previous = row['first_blocker']
        if run_length:
            runs[run_length] += 1
    return dict(exact_evaluations=total, repeated_same_blocker=repeated,
                repeated_fraction=round(repeated / max(total, 1), 4),
                repeats_per_route=round(repeated / max(len(by_route), 1), 1),
                max_repeat_run=max(runs) if runs else 0,
                run_length_histogram=dict(sorted(runs.items())[:20]))


# ---------------------------------------------------------------------------
# Q8: spacing rejection distances and corrected-policy rescue on samples
# ---------------------------------------------------------------------------
def spacing_distance_distribution(exact_rows):
    distances = [row['distance'] for row in exact_rows
                 if row['reason'] == 'spacing_pairs' and row['distance'] is not None]
    edges = [(0.0, 0.01), (0.01, 0.05), (0.05, 0.10), (0.10, 0.13), (0.13, 0.15),
             (0.15, 0.155), (0.155, 0.16), (0.16, 0.165), (0.165, 0.17),
             (0.17, 0.172), (0.172, 0.174), (0.174, 0.1749), (0.1749, 0.1750001)]
    histogram = Counter()
    for d in distances:
        for lo, hi in edges:
            if lo <= d < hi:
                histogram[f'[{lo},{hi})'] += 1
                break
        else:
            histogram['outside'] += 1
    deficit = [0.175 - d for d in distances]
    return dict(n=len(distances),
                min_distance=round(min(distances), 8) if distances else None,
                max_distance=round(max(distances), 8) if distances else None,
                mean_deficit=round(float(np.mean(deficit)), 8) if deficit else None,
                deficit_bins=dict(histogram),
                share_deficit_le_5um=round(float(np.mean([x <= 0.005 for x in deficit])), 4) if deficit else None,
                share_deficit_le_1um=round(float(np.mean([x <= 0.001 for x in deficit])), 4) if deficit else None,
                share_distance_ge_0p174=round(float(np.mean([d >= 0.174 for d in distances])), 4) if distances else None)


def spacing_sample_analysis(exact_rows, accepted, routes, endpoints, limit_per_pair=120):
    """For a sample of spacing-rejected candidates of the deployed baseline
    replay, rebuild the candidate and the first blocker and classify:
    deployed violation cause vs corrected-policy decision; whether an arc is
    involved; the exact-window / primitive-pair rescue."""
    by_id = {r['route_id']: r for r in routes}
    built_cache = {}
    accepted_prepared = {rid: P.prepare(rec['primitives']) for rid, rec in accepted.items()}

    def build_candidate(row):
        route = by_id[row['route_id']]
        src = endpoints[route['source_endpoint']]
        dst = endpoints[route['target_endpoint']]
        p, q, transform, kind = C.canonicalize(src['side'], dst['side'],
                                               src['routing_xy'], dst['routing_xy'])
        p, q = np.asarray(p), np.asarray(q)
        y = row['y']
        try:
            local = C.opposite(p, q, y, radius=5., width=.05) if kind == 'opposite' \
                else C.adjacent(p, q, y, radius=5., width=.05)
        except ValueError:
            return None
        prim = C.transform_primitives(local, transform, inverse=True)
        return P.prepare(prim)

    sample = []
    grouped = defaultdict(list)
    for row in exact_rows:
        if row['reason'] != 'spacing_pairs' or row['first_blocker'] is None:
            continue
        grouped[by_id[row['route_id']]['pair']].append(row)
    rng = __import__('random').Random(42)
    for pair, rows in grouped.items():
        if len(rows) > limit_per_pair:
            rows = rng.sample(rows, limit_per_pair)
        sample.extend(rows)
    results = Counter()
    classification = Counter()
    examples = []
    for row in sample:
        candidate = build_candidate(row)
        if candidate is None:
            results['bend_fail'] += 1
            continue
        blocker = accepted_prepared.get(row['first_blocker'])
        if blocker is None:
            results['no_blocker_geometry'] += 1
            continue
        deployed = P.pair_check_deployed(candidate, blocker)
        exact = P.pair_check_exact_window(candidate, blocker)
        pp = P.pair_check_primitive_pair(candidate, blocker)
        kinds = Counter()
        if deployed.get('valid'):
            results['deployed_says_legal'] += 1
            continue
        # identify involved primitive kinds
        crossings, _ = P.collect_crossings(candidate, blocker)
        for c in crossings:
            kinds[(candidate.primitives[c['i']].kind, blocker.primitives[c['j']].kind)] += 1
        has_arc = any('arc' in key for key in kinds)
        deficit = 0.175 - deployed['distance'] if deployed.get('distance') is not None else None
        key = ('crossing' if crossings else 'no_crossing',
               'arc_involved' if has_arc else 'line_line',
               'corrected_legal' if (exact['valid'] or pp['valid']) else 'genuinely_illegal')
        classification['|'.join(key)] += 1
        if deficit is not None:
            classification[f'deficit_bucket_' + ('<=5um' if deficit <= 0.005 else '>5um')] += 1
        examples.append(dict(route_id=row['route_id'], blocker=row['first_blocker'],
                             pair=by_id[row['route_id']]['pair'],
                             distance=deployed.get('distance'),
                             crossings=len(crossings),
                             kinds=dict((f'{a}|{b}', v) for (a, b), v in kinds.items()),
                             exact_window_legal=bool(exact['valid']),
                             primitive_pair_legal=bool(pp['valid']),
                             corrected_legal=bool(exact['valid'] or pp['valid'])))
    classified = sum(v for k, v in classification.items() if not k.startswith('deficit_bucket'))
    corrected = sum(v for k, v in classification.items()
                    if k.endswith('corrected_legal') and not k.startswith('deficit_bucket'))
    return dict(sample_size=len(sample),
                outcomes=dict(sorted(classification.items())),
                corrected_legal=corrected,
                corrected_legal_fraction=round(corrected / max(classified, 1), 4),
                examples=[e for e in examples if e['corrected_legal']][:12])


# ---------------------------------------------------------------------------
# Q7: WGyset / track state semantics, measured on accepted routes
# ---------------------------------------------------------------------------
def track_usage(accepted):
    routes, _, _, _ = C.load_inputs()
    pair_by_id = {r['route_id']: r['pair'] for r in routes}
    rows = []
    for rec in accepted.values():
        rows.append(dict(route_id=rec['route_id'], pair=pair_by_id.get(rec['route_id']),
                         track_index=rec.get('track_index'), track_mm=rec.get('track_mm'),
                         legacy_pass=rec.get('legacy_pass'), interface_mode=rec.get('interface_mode')))
    by_pair = defaultdict(list)
    for row in rows:
        by_pair[row['pair']].append(row)
    out = {}
    for pair, items in by_pair.items():
        tracks = Counter(round(item['track_mm'], 6) for item in items if item['track_mm'] is not None)
        out[pair] = dict(accepted=len(items),
                         distinct_track_y=len(tracks),
                         tracks_shared_by_multiple_routes=sum(1 for v in tracks.values() if v > 1),
                         interface_modes=dict(Counter(item['interface_mode'] for item in items)),
                         track_index_min=min((item['track_index'] for item in items
                                              if item['track_index'] is not None), default=None),
                         track_index_max=max((item['track_index'] for item in items
                                              if item['track_index'] is not None), default=None))
    return out


def cross_group_blocking(exact_rows, pair_by_id):
    """Q7/Q1: how often the first blocker belongs to a different pair group than
    the candidate (noCross only sees the current group, so cross-group blocking
    can only be caught by the global exact index)."""
    totals = Counter()
    cross = Counter()
    for row in exact_rows:
        if row['first_blocker'] is None:
            continue
        pair = pair_by_id.get(row['route_id'])
        blocker_pair = pair_by_id.get(row['first_blocker'])
        if pair is None or blocker_pair is None:
            continue
        totals[pair] += 1
        cross[pair] += int(pair != blocker_pair)
    return {pair: dict(first_blocker_events=totals[pair], cross_group=cross[pair],
                       cross_group_fraction=round(cross[pair] / max(totals[pair], 1), 4))
            for pair in totals}


def write_tables(result, replays):
    """Persist the per-pair tables quoted by the report."""
    tables = DATA / 'tables'
    tables.mkdir(parents=True, exist_ok=True)
    # Q1/Q5 per-pair table from the budget-free baseline-order replay
    payload = replays.get('full_unlimited')
    if payload:
        exact_by_pair = defaultdict(Counter)
        for row in read_exact_csv(DATA / 'replay' / 'full_unlimited_exact.csv'):
            exact_by_pair[row['route_id']]['n'] += 1
            if row['reason']:
                exact_by_pair[row['route_id']][row['reason']] += 1
        pair_by_id = {r['route_id']: r['pair'] for r in C.load_inputs()[0]}
        rows = []
        distances = defaultdict(list)
        for row in payload['route_rows']:
            pair = row['pair']
            entry = dict(pair=pair, route_id=row['route_id'], rank=row['rank_in_group'],
                         scanned=row['scanned'], order_fail=row['order_fail'],
                         nocross_fail=row['nocross_fail'], bend_fail=row['bend_fail'],
                         validate_fail=row['validate_fail'], exact=row['exact'],
                         accepted=row['accepted'],
                         first_blocker=row['first_blocker'],
                         nearest_blocked_distance=row['nearest_blocked_distance'])
            for key in ('spacing_pairs', 'overlap_pairs', 'touch_pairs',
                        'crossing_zone_overlap_pairs'):
                entry[key] = row['rejection_counts'].get(key, 0)
            rows.append(entry)
            if row['nearest_blocked_distance'] is not None:
                distances[pair].append(row['nearest_blocked_distance'])
        with (tables / 'q1_route_rows.csv').open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        summary = []
        for pair in ('SW', 'ES', 'NW', 'EN', 'NS', 'EW'):
            items = [r for r in rows if r['pair'] == pair]
            accepted = sum(r['accepted'] for r in items)
            scanned = sum(r['scanned'] for r in items)
            dist = distances.get(pair, [])
            summary.append(dict(
                pair=pair, attempted=len(items), accepted=accepted,
                mean_scanned=round(scanned / max(len(items), 1), 1),
                mean_exact=round(sum(r['exact'] for r in items) / max(len(items), 1), 1),
                order_fail=sum(r['order_fail'] for r in items),
                nocross_fail=sum(r['nocross_fail'] for r in items),
                bend_fail=sum(r['bend_fail'] for r in items),
                exact=sum(r['exact'] for r in items),
                spacing=sum(r['spacing_pairs'] for r in items),
                overlap=sum(r['overlap_pairs'] for r in items),
                touch=sum(r['touch_pairs'] for r in items),
                zone=sum(r['crossing_zone_overlap_pairs'] for r in items),
                nearest_blocked_median=round(float(np.median(dist)), 6) if dist else None,
                nearest_blocked_p10=round(float(np.percentile(dist, 10)), 6) if dist else None,
                nearest_blocked_max=round(max(dist), 6) if dist else None))
        with (tables / 'q1_by_pair.csv').open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(summary[0]))
            writer.writeheader()
            writer.writerows(summary)
        result['q1_by_pair_table'] = summary
    # Q8 spacing-distance distribution CSV
    for label, key in (('q8_spacing_full.csv', 'q8_spacing_distances'),
                       ('q8_spacing_baseline_667.csv', 'q8_spacing_distances_baseline_667')):
        if key in result:
            with (tables / label).open('w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['distance_bin', 'count'])
                for name, count in result[key]['deficit_bins'].items():
                    writer.writerow([name, count])


def main():
    routes, endpoints, _, _ = C.load_inputs()
    baseline_accepted = {}
    for rec in json.loads((C.BASELINE / 'routes_geometry.json').read_text(encoding='utf-8'))['routes']:
        baseline_accepted[rec['route_id']] = rec
    sc = json.loads((C.BASELINE / 'search_checkpoint.json').read_text(encoding='utf-8'))
    stats = json.loads((C.BASELINE / 'statistics.json').read_text(encoding='utf-8'))

    replays = {}
    for label in ('full_unlimited', 'order_adjacent_only', 'order_opposite_only', 'order_opposite_first'):
        payload = load_json(DATA / 'replay' / f'{label}.json')
        if payload:
            replays[label] = payload
    policy = load_json(DATA / 'policy_search' / 'policyC_full_unlimited.json')

    result = dict(schema='d56_diag_analysis_v1',
                  baseline=dict(success=stats['success_count'], failed=stats['failed_count'],
                                attempted=stats['actual_routing_attempted_count'],
                                not_attempted=stats['not_attempted_due_global_budget'],
                                evaluations=stats['search']['candidate_evaluations'],
                                scanned=stats['search']['scanned_tracks'],
                                rejection_counts=stats['failed_track_rejection_counts'],
                                group_order=stats['search']['group_order'],
                                elapsed=stats['total_runtime_seconds']))
    # Q1: replay comparison
    q1 = {}
    for label, payload in replays.items():
        q1[label] = dict(accepted=payload['summary']['accepted'],
                         attempted=payload['summary']['attempted'],
                         elapsed=round(payload['summary']['elapsed_seconds'], 1),
                         by_pair=payload['summary']['by_pair'],
                         per_pair_stats=replay_stats(payload))
    # baseline order unlimited (full_unlimited) gives the budget-free reference
    if 'full_unlimited' in replays:
        q1['full_unlimited']['first_blocker_table'] = first_blocker_table(replays['full_unlimited']['route_rows'])
        q1['full_unlimited']['blocker_concentration'] = blocker_share_gini(replays['full_unlimited']['route_rows'])
        q1['full_unlimited']['baseline_comparison'] = replays['full_unlimited'].get('baseline_comparison')
    result['q1_order_replay'] = q1
    if policy:
        result['policyC_full_run'] = policy['summary']

    # Q5: from full replay exact log if available, else from per-route counters
    exact_rows = read_exact_csv(DATA / 'replay' / 'full_unlimited_exact.csv')
    baseline_attempted_ids = set(baseline_accepted) | {
        int(row['route_id']) for row in sc['failed'] if row.get('evaluated', 0) > 0}
    if exact_rows:
        baseline_exact = [row for row in exact_rows if row['route_id'] in baseline_attempted_ids]
        pair_by_id = {r['route_id']: r['pair'] for r in routes}
        result['q5_exact_evaluations'] = redundancy(exact_rows)
        result['q5_exact_evaluations_baseline_667'] = redundancy(baseline_exact)
        result['q8_spacing_distances'] = spacing_distance_distribution(exact_rows)
        result['q8_spacing_distances_baseline_667'] = spacing_distance_distribution(baseline_exact)
        result['q8_spacing_sample_rescue'] = spacing_sample_analysis(
            baseline_exact, baseline_accepted, routes, endpoints)
        result['q7_cross_group_blocking'] = cross_group_blocking(baseline_exact, pair_by_id)
    # per-pair scan/eval table (baseline-equivalent from deployed statistics)
    result['q5_deployed_statistics'] = dict(
        scanned=stats['search']['scanned_tracks'],
        evaluations=stats['search']['candidate_evaluations'],
        early_exit=int(stats['search']['scanned_tracks']) - int(stats['search']['candidate_evaluations']),
        early_exit_fraction=round(1 - stats['search']['candidate_evaluations']
                                  / stats['search']['scanned_tracks'], 4),
        mean_scans_per_attempted_route=round(stats['search']['scanned_tracks']
                                             / stats['actual_routing_attempted_count'], 1),
        mean_evaluations_per_attempted_route=round(stats['search']['candidate_evaluations']
                                                   / stats['actual_routing_attempted_count'], 1),
        rejection_counts=stats['failed_track_rejection_counts'])
    # budget utilisation (Q8/F)
    result['budget'] = dict(
        total_runtime_seconds=stats['total_runtime_seconds'],
        search_runtime_seconds=stats['search']['search_runtime_seconds'],
        candidate_evaluations=stats['search']['candidate_evaluations'],
        evaluation_budget=900000,
        evaluation_budget_used_fraction=round(stats['search']['candidate_evaluations'] / 900000, 4),
        time_budget_seconds=600,
        not_attempted_routes=stats['not_attempted_due_global_budget'],
        per_group_durations={g['pair']: round(g['duration_seconds'], 2)
                             for g in stats['search']['groups']})
    # Q2 / Q4: sampled rule rejections from the full replay
    sample_rows = read_samples_csv(DATA / 'replay' / 'full_unlimited_samples.csv')
    if sample_rows:
        q24 = {}
        for phase in ('order_reject', 'nocross_reject'):
            subset = [row for row in sample_rows if row['phase'] == phase]
            if not subset:
                continue
            bend_fit = sum(row['bend_fit'] == 'True' for row in subset)
            validate_ok = sum(row['validate_ok'] == 'True' for row in subset)
            legal = sum(row['exact_valid'] == 'True' for row in subset)
            by_pair = defaultdict(lambda: Counter())
            for row in subset:
                by_pair[row['pair']]['sampled'] += 1
                by_pair[row['pair']]['legal'] += int(row['exact_valid'] == 'True')
            q24[phase] = dict(
                sampled=len(subset), bend_fits=bend_fit,
                bend_fit_fraction=round(bend_fit / len(subset), 4),
                validate_ok_fraction=round(validate_ok / len(subset), 4),
                exact_legal=legal, exact_legal_fraction=round(legal / len(subset), 4),
                by_pair={pair: dict(sampled=c['sampled'], legal=c['legal'],
                                    legal_fraction=round(c['legal'] / max(c['sampled'], 1), 4))
                         for pair, c in by_pair.items()})
        total_order = stats['failed_track_rejection_counts'].get('original_track_endpoint_order', 0)
        total_nocross = stats['failed_track_rejection_counts'].get('original_noCross', 0)
        if 'order_reject' in q24:
            q24['estimated_wrong_order_rejections'] = round(
                total_order * q24['order_reject']['exact_legal_fraction'], 1)
        if 'nocross_reject' in q24:
            q24['estimated_wrong_nocross_rejections'] = round(
                total_nocross * q24['nocross_reject']['exact_legal_fraction'], 1)
        q24['total_order_rejections'] = total_order
        q24['total_nocross_rejections'] = total_nocross
        result['q2_q4_rule_rejection_samples'] = q24
    # Q7
    result['q7_track_usage'] = track_usage(baseline_accepted)
    write_tables(result, replays)
    C.save_json(DATA / 'analysis.json', result)
    print(json.dumps(dict(
        baseline=result['baseline'],
        q1={label: dict(accepted=v['accepted'], attempted=v['attempted'],
                        by_pair=v['by_pair']) for label, v in q1.items()
            if label != 'full_unlimited' or 'first_blocker_table' not in v},
        q1_full_accepted=q1.get('full_unlimited', {}).get('accepted'),
        policyC=result.get('policyC_full_run'),
        q5=result.get('q5_exact_evaluations'),
        q8=result.get('q8_spacing_distances'),
        q8_sample=({k: v for k, v in result['q8_spacing_sample_rescue'].items()
                    if k != 'examples'} if 'q8_spacing_sample_rescue' in result else None),
        q24=result.get('q2_q4_rule_rejection_samples'),
        q7=result.get('q7_track_usage')), indent=2, default=str))


if __name__ == '__main__':
    main()
