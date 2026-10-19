"""Q8 / Lead's request: how many routes the baseline algorithm recovers when the
crossing-zone exemption is computed correctly (instead of the straight-line
formula applied to arcs).

Runs the *identical* legacy first-free / noCross / D56-template search (same
group order, same candidate stream, same deterministic route order, unlimited
budget) but replaces only the exact conflict engine:

  --policy primitive_pair   Lead's upper-bound policy: whole primitive-pair
                            exemption for a single transversal crossing
  --policy exact_window     defensible policy: exemption arclength computed from
                            the real curve geometry by bisection

Baseline for comparison: 80/1024 with the deployed policy (outputs/
four_side_1024_legacy_two_branch_v2) and the budget-free deployed replay
(scratch/diagnosis/data/replay/full_unlimited.json).

Usage (from OpticalWaveguideRouter2D):
  .venv/Scripts/python.exe scratch/diagnosis/probe_policy_search.py --policy primitive_pair
  .venv/Scripts/python.exe scratch/diagnosis/probe_policy_search.py --policy exact_window --pairs SW,ES,NW,EN
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import d56_diag_common as C
from policy_search import PolicyIndex


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--policy', default='primitive_pair', choices=['primitive_pair', 'exact_window'])
    ap.add_argument('--label', default=None)
    ap.add_argument('--pairs', default=','.join(C.GROUP_ORDER))
    ap.add_argument('--stop-after', type=int, default=None)
    ap.add_argument('--template', default='legacy', choices=['legacy', 'flex'])
    ap.add_argument('--flex-routes', default=None,
                    help='JSON file mapping route_id -> [[t1,t2],...] for template=flex')
    ap.add_argument('--seed-accepted', default=None,
                    help='replay JSON whose accepted routes seed the index (rescue runs)')
    ap.add_argument('--route-order', default='baseline', choices=['baseline', 'route_id', 'custom'],
                    help='baseline = legacy per-group -canonical(source x); route_id = global id order')
    ap.add_argument('--only-routes', default=None,
                    help='comma list of route ids: when set, only these are attempted, in the given order')
    ap.add_argument('--out-dir', default=str(C.DATA / 'policy_search'))
    return ap.parse_args(argv)


def main():
    args = parse_args()
    pairs = [p for p in args.pairs.split(',') if p]
    label = args.label or f'{args.policy}_{args.template}'
    routes, endpoints, _, _ = C.load_inputs()
    cfg = C.config()
    contexts = C.build_contexts(routes, endpoints, cfg, pairs=pairs)
    engine = PolicyIndex(policy=args.policy)
    recorder = C.SearchRecorder(record_exact=False)
    if args.seed_accepted:
        seed = json.loads(Path(args.seed_accepted).read_text(encoding='utf-8'))
        for rec in seed['accepted']:
            engine.add(rec['route_id'], rec['primitives'])
    # flexible candidates
    flex_candidates = None
    template = args.template
    if template == 'flex':
        flex_map = json.loads(Path(args.flex_routes).read_text(encoding='utf-8'))
        flex_candidates = {int(k): [tuple(v) for v in values] for k, values in flex_map.items()}
    only = [int(x) for x in args.only_routes.split(',')] if args.only_routes else None
    if only is not None:
        # custom order: synthesize group contexts restricted to the ordered subset
        by_id = {r['route_id']: r for r in routes}
        order_pairs = []
        for rid in only:
            pair = by_id[rid]['pair']
            if pair not in order_pairs:
                order_pairs.append(pair)
        contexts = C.build_contexts(routes, endpoints, cfg, pairs=order_pairs)
    searcher = C.Searcher(contexts, routes, endpoints, cfg, None, recorder,
                          sample_stride=0, stop_after=args.stop_after, template=template,
                          flex_candidates=flex_candidates,
                          evaluator=engine.evaluate, register=engine.add)
    t0 = time.perf_counter()
    if only is not None:
        searcher.run_custom(only)
    else:
        searcher.run(pairs)
    elapsed = time.perf_counter() - t0
    summary = dict(label=label, policy=args.policy, template=template, pairs=pairs,
                   attempted=len(recorder.route_rows), accepted=len(recorder.accepted),
                   elapsed_seconds=elapsed,
                   by_pair={pair: dict(attempted=sum(1 for r in recorder.route_rows if r['pair'] == pair),
                                       accepted=sum(1 for r in recorder.route_rows if r['pair'] == pair and r['accepted']))
                            for pair in pairs},
                   rejection_counts=dict(recorder.rejections),
                   checked_pairs=engine.checked_pairs,
                   seed_accepted=args.seed_accepted)
    payload = dict(summary=summary, route_rows=recorder.route_rows,
                   accepted=list(recorder.accepted.values()))
    out = Path(args.out_dir) / f'{label}.json'
    C.save_json(out, payload)
    print(json.dumps(summary, indent=2))


def _run_custom(searcher, contexts, routes, endpoints, ordered_ids):
    """Kept for backwards compatibility: delegate to ``Searcher.run_custom``."""
    searcher.run_custom(ordered_ids)


if __name__ == '__main__':
    main()
