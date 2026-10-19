"""Phase-1 diagnostic: are the CSV-designed direct D56 L paths mutually legal?

Reads the immutable CSV, builds every *adjacent* connection's direct L path
(with the original R=5 quarter-arc construction), and tests all pairs with the
exact ConflictIndex.  Also reports per-group fits and the first blockers.
"""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from four_side_1024.inputs import load, DEFAULT_INPUT
from four_side_1024.legacy_geometry import canonicalize, transform_primitives, adjacent, opposite
from four_side_1024.conflicts import ConflictIndex
from four_side_1024.geometry import validate, length


def build_adjacent(routes, endpoints):
    out = {}
    for r in routes:
        if r['relation'] != 'adjacent':
            continue
        src = endpoints[r['source_endpoint']]
        dst = endpoints[r['target_endpoint']]
        p, q, transform, kind = canonicalize(src['side'], dst['side'],
                                             src['routing_xy'], dst['routing_xy'])
        assert kind == 'adjacent', (r['route_id'], kind)
        p = np.asarray(p); q = np.asarray(q)
        try:
            local = adjacent(p, q, float(q[1]), radius=5., width=.05)
            prim = transform_primitives(local, transform, inverse=True)
            errs = validate(prim, src['routing_xy'], dst['routing_xy'], src['inward'],
                            -np.array(dst['inward']), board=150., width=.05, min_radius=5.)
        except ValueError as exc:
            out[r['route_id']] = ('error', str(exc), r['pair'])
            continue
        if errs:
            out[r['route_id']] = ('invalid', errs, r['pair'])
        else:
            out[r['route_id']] = ('ok', prim, r['pair'])
    return out


def main():
    routes, endpoints, _, _ = load(DEFAULT_INPUT)
    by_id = {r['route_id']: r for r in routes}
    built = build_adjacent(routes, endpoints)
    ok = {k: v for k, v in built.items() if v[0] == 'ok'}
    print('adjacent routes:', len(built), 'direct-L valid geometry:', len(ok),
          'errors:', Counter(v[0] for v in built.values()))
    for k, v in list(built.items()):
        if v[0] != 'ok':
            print('  failed', k, v[2], v[1])
    index = ConflictIndex(width=.05, gap=.125, sagitta=.0005)
    placed = {}
    reject = Counter()
    failures = []
    for rid, (state, prim, pair) in ok.items():
        res = index.evaluate(prim)
        if res['valid']:
            index.add(rid, prim)
            placed[rid] = prim
        else:
            reasons = tuple(sorted(k for k in ('spacing_pairs', 'overlap_pairs', 'touch_pairs',
                                               'crossing_zone_overlap_pairs')
                                   if res.get(k)))
            reject[reasons] += 1
            failures.append((rid, pair, reasons, res.get('crossing_zone_overlap_pairs')))
    print('sequential placement of direct L:', len(placed), '/', len(ok),
          'rejections:', dict(reject))
    # Full pairwise audit of the whole designed set (independent of order).
    allp = ConflictIndex(width=.05, gap=.125, sagitta=.0005)
    for rid, (state, prim, pair) in ok.items():
        allp.add(rid, prim)
    bad = 0
    badpairs = []
    ids = list(allp.routes)
    # evaluate route-by-route against all others
    for rid in ids:
        res = allp.evaluate(allp.routes[rid].primitives, exclude=None, stop_on_invalid=True) if False else \
              allp.evaluate(built[rid][1], exclude=rid, stop_on_invalid=True)
        if not res['valid']:
            bad += 1
            badpairs.append((rid, tuple(sorted(k for k in ('spacing_pairs', 'overlap_pairs',
                                                           'touch_pairs', 'crossing_zone_overlap_pairs')
                                              if res.get(k)))))
    print('mutually illegal adjacent routes:', bad, '/', len(ids))
    print('reason histogram:', Counter(b[1] for b in badpairs))
    print('examples:', badpairs[:20])
    print('failure examples:', failures[:20])
    # per pair-type mutual legality
    per = defaultdict(lambda: [0, 0])
    for rid in ids:
        per[by_id[rid]['pair']][0] += 1
    for rid, reason in badpairs:
        per[by_id[rid]['pair']][1] += 1
    print('per pair [total, illegal]:', dict(per))


if __name__ == '__main__':
    main()
