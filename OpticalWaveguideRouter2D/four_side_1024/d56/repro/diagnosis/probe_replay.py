"""Instrumented, budget-free replay of the legacy four-side D56 baseline (80/1024).

Two jobs:
1. validate that this replay reproduces the deployed baseline *exactly* on the
   666 routes the 600 s budget fully processed (baseline route 155 was
   interrupted mid-scan and is excluded from the comparison);
2. produce per-route / per-candidate instrumentation used by every other probe:
   candidate scan counts, early-exit attribution, first blocker + nearest
   blocked distance, exact-evaluation log, rule-rejected candidate samples, and
   the unlimited-budget success count.

Usage (from OpticalWaveguideRouter2D):
  .venv/Scripts/python.exe scratch/diagnosis/probe_replay.py --label full_unlimited
  .venv/Scripts/python.exe scratch/diagnosis/probe_replay.py --label baseline_666 --stop-after 666
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter, OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import d56_diag_common as C


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--label', required=True)
    ap.add_argument('--pairs', default=','.join(C.GROUP_ORDER),
                    help='comma ordered pair groups to process, e.g. SW,ES,NW,EN,NS,EW')
    ap.add_argument('--stop-after', type=int, default=None,
                    help='stop after this many route attempts (baseline replay)')
    ap.add_argument('--sample-stride', type=int, default=6,
                    help='keep every k-th rule-rejected candidate; 0 disables')
    ap.add_argument('--exact-log', action='store_true', default=True)
    ap.add_argument('--no-exact-log', dest='exact_log', action='store_false')
    ap.add_argument('--out-dir', default=str(C.DATA / 'replay'))
    ap.add_argument('--validate-baseline', action='store_true')
    return ap.parse_args(argv)


def compare_with_baseline(route_rows, accepted, failed, baseline_accepted=None):
    """Compare replay decisions on routes the baseline fully processed."""
    failed_by_id = {r['route_id']: r for r in failed}
    accepted_ids = set(accepted)
    mismatched, not_comparable, compared = [], [], 0
    for row in route_rows:
        rid = row['route_id']
        base = failed_by_id.get(rid)
        if rid in accepted_ids:
            if base is not None and base.get('evaluated', 0) == 0:
                mismatched.append(dict(route_id=rid, kind='replay_accept_baseline_not_attempted'))
            continue
        if base is None:
            mismatched.append(dict(route_id=rid, kind='replay_fail_but_baseline_accepted'))
            continue
        if base.get('evaluated', 0) == 0:
            not_comparable.append(rid)  # baseline budget did not attempt it
            continue
        if rid == 155:  # baseline interrupted mid-scan
            not_comparable.append(rid)
            continue
        compared += 1
        diffs = {}
        if row['scanned'] != base['scanned_tracks']:
            diffs['scanned'] = [row['scanned'], base['scanned_tracks']]
        if row['exact'] != base['evaluated']:
            diffs['exact'] = [row['exact'], base['evaluated']]
        base_rej = {k: v for k, v in base.get('rejection_counts', {}).items()
                    if k != 'search_budget_exhausted'}
        replay_rej = dict(row['rejection_counts'])
        replay_rej.pop('search_budget_exhausted', None)
        if replay_rej != base_rej:
            diffs['rejection_counts'] = [replay_rej, base_rej]
        base_blockers = {int(k): v for k, v in base.get('blockers', {}).items()}
        replay_blockers = {int(k): v for k, v in row['blockers'].items()}
        if replay_blockers != base_blockers:
            diffs['blockers'] = [replay_blockers, base_blockers]
        if diffs:
            mismatched.append(dict(route_id=rid, kind='diff', **diffs))
    # accepted-route geometry comparison for routes both runs accepted
    accepted_mismatch = []
    if baseline_accepted:
        for rid, rec in accepted.items():
            base = baseline_accepted.get(rid)
            if base is None:
                accepted_mismatch.append(dict(route_id=rid, kind='not_in_baseline'))
                continue
            same = (len(base['primitives']) == len(rec['primitives']) and all(
                abs(base['primitives'][i]['p0'][0] - rec['primitives'][i]['p0'][0]) < 1e-9 and
                abs(base['primitives'][i]['p0'][1] - rec['primitives'][i]['p0'][1]) < 1e-9 and
                abs(base['primitives'][i]['p1'][0] - rec['primitives'][i]['p1'][0]) < 1e-9 and
                abs(base['primitives'][i]['p1'][1] - rec['primitives'][i]['p1'][1]) < 1e-9
                for i in range(len(base['primitives']))))
            if not same:
                accepted_mismatch.append(dict(route_id=rid, kind='geometry_diff'))
    return dict(compared=compared, mismatched=mismatched, not_comparable=not_comparable,
                accepted_replay=len(accepted), accepted_mismatch=accepted_mismatch)


def main():
    args = parse_args()
    out_dir = Path(args.out_dir)
    pairs = [p for p in args.pairs.split(',') if p]
    routes, endpoints, connectors, validation = C.load_inputs()
    cfg = C.config()
    contexts = C.build_contexts(routes, endpoints, cfg, pairs=pairs)
    index = C.fresh_index(cfg)
    recorder = C.SearchRecorder(record_exact=args.exact_log)
    searcher = C.Searcher(contexts, routes, endpoints, cfg, index, recorder,
                          sample_stride=args.sample_stride, stop_after=args.stop_after,
                          template='legacy', flex_candidates=None)
    t0 = time.perf_counter()
    searcher.run(pairs)
    elapsed = time.perf_counter() - t0
    accepted = OrderedDict((rid, rec) for rid, rec in recorder.accepted.items())
    summary = dict(label=args.label, pairs=pairs, stop_after=args.stop_after,
                   attempted=len(recorder.route_rows), accepted=len(accepted), elapsed_seconds=elapsed,
                   evaluations=recorder.evaluations,
                   scanned=sum(r['scanned'] for r in recorder.route_rows),
                   rejection_counts=dict(recorder.rejections),
                   phase_counts=dict(
                       order_fail=sum(r['order_fail'] for r in recorder.route_rows),
                       nocross_fail=sum(r['nocross_fail'] for r in recorder.route_rows),
                       bend_fail=sum(r['bend_fail'] for r in recorder.route_rows),
                       validate_fail=sum(r['validate_fail'] for r in recorder.route_rows),
                       exact=sum(r['exact'] for r in recorder.route_rows),
                       exact_reject=sum(r['exact_reject'] for r in recorder.route_rows)),
                   timings=dict(recorder.times),
                   by_pair={pair: dict(attempted=sum(1 for r in recorder.route_rows if r['pair'] == pair),
                                       accepted=sum(1 for r in recorder.route_rows if r['pair'] == pair and r['accepted']))
                            for pair in pairs})
    payload = dict(config=dict(pairs=pairs, stop_after=args.stop_after, budget='unlimited',
                               width_mm=cfg['width_mm'], edge_gap_mm=cfg['edge_gap_mm'],
                               min_radius_mm=cfg['min_radius_mm'], sagitta_mm=cfg['sagitta_mm']),
                   summary=summary,
                   route_rows=recorder.route_rows,
                   accepted=list(accepted.values()),
                   samples=recorder.samples,
                   times=dict(recorder.times))
    if args.validate_baseline:
        sc, rg, stats = C.load_baseline()
        baseline_accepted = {rec['route_id']: rec for rec in rg['routes']}
        payload['baseline_comparison'] = compare_with_baseline(
            recorder.route_rows, accepted, sc['failed'], baseline_accepted)
        cmp = payload['baseline_comparison']
        print('baseline comparison: compared=', cmp['compared'],
              'mismatch_count=', len(cmp['mismatched']),
              'accepted_mismatch=', len(cmp['accepted_mismatch']))
        print('first mismatches:', json.dumps(cmp['mismatched'][:5]))
        print('accepted mismatch:', json.dumps(cmp['accepted_mismatch'][:5]))
    C.save_json(out_dir / f'{args.label}.json', payload)
    if args.exact_log and recorder.exact:
        with (out_dir / f'{args.label}_exact.csv').open('w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['route_id', 'track_index', 'y', 'reason', 'first_blocker', 'distance', 'n_blockers'])
            for row in recorder.exact:
                w.writerow(row)
    if recorder.samples:
        with (out_dir / f'{args.label}_samples.csv').open('w', newline='', encoding='utf-8') as f:
            fields = sorted({k for s in recorder.samples for k in s})
            w = csv.DictWriter(f, fields)
            w.writeheader()
            for s in recorder.samples:
                w.writerow({k: s.get(k) for k in fields})
    print(json.dumps(dict(label=args.label, attempted=summary['attempted'],
                          accepted=summary['accepted'], elapsed=round(elapsed, 1),
                          evaluations=summary['evaluations'], timings=summary['timings'],
                          phase_counts=summary['phase_counts']), indent=2))


if __name__ == '__main__':
    main()
