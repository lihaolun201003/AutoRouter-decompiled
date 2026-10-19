"""Quick smoke test of the D56 engine on relation subsets."""
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from four_side_1024.inputs import load, DEFAULT_INPUT
from four_side_1024.d56.frames import build_frames
from four_side_1024.d56.search import Router


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--subset', default='all', choices=['all', 'adjacent', 'opposite'])
    ap.add_argument('--order', default='x_desc')
    ap.add_argument('--pairs', default='')
    ap.add_argument('--budget', type=int, default=0)
    ap.add_argument('--ripup', type=int, default=0)
    ap.add_argument('--limit', type=int, default=0, help='only first N routes of subset')
    args = ap.parse_args()
    routes, endpoints, _, _ = load(DEFAULT_INPUT)
    frames = build_frames(routes, endpoints)
    if args.subset != 'all':
        routes = [r for r in routes if r['relation'] == args.subset]
    if args.pairs:
        wanted = set(args.pairs.split(','))
        routes = [r for r in routes if r['pair'] in wanted]
    if args.limit:
        routes = routes[:args.limit]
    cfg = dict(within_group=args.order,
               early_deep=False,
               no_deep=False)
    if args.budget:
        cfg['candidate_budget_per_route'] = args.budget
    router = Router(frames, routes, cfg=cfg, log=print)
    t = time.perf_counter()
    strategy = dict(name='test', group_order=['NS', 'EW', 'EN', 'ES', 'SW', 'NW'],
                    within_group=args.order)
    stats = router.run(strategy)
    print('run:', stats, 'wall=%.1fs' % (time.perf_counter() - t))
    rip = None
    if args.ripup:
        rip = router.ripup(max_rounds=args.ripup)
        print('ripup:', rip)
    by_pair = Counter()
    fail_reason = Counter()
    for rid, result in router.accepted.items():
        by_pair[frames[rid].pair] += 1
    for rid, failure in router.failed.items():
        fail_reason[failure['reason']] += 1
    print('accepted by pair:', dict(by_pair))
    print('accepted by relation:', Counter(r['relation'] for r in routes
                                          if r['route_id'] in router.accepted))
    print('fail reasons:', dict(fail_reason))
    rej = Counter()
    for failure in router.failed.values():
        rej.update(failure['rejection_counts'])
    print('rejection counts:', dict(rej))
    print('evals', router.index.evaluations, 'index s %.1f' % router.index.index_seconds,
          'exact s %.1f' % router.index.exact_seconds)
    total_len = sum(result.length_mm for result in router.accepted.values())
    crossings = sum(result.crossings for result in router.accepted.values())
    print('mean length %.2f total %.1f crossings %d' % (
        total_len / max(1, len(router.accepted)), total_len, crossings))
    out = Path('scratch/d56_smoke_result.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(dict(
        subset=args.subset, order=args.order,
        accepted=sorted(router.accepted), failed=sorted(router.failed),
        total=len(routes)), indent=0), encoding='utf-8')


if __name__ == '__main__':
    main()
