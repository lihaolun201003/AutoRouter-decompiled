"""Phase-1 diagnostic: classify the mutual conflicts among the CSV's designed direct-L paths."""
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from four_side_1024.inputs import load, DEFAULT_INPUT
from four_side_1024.legacy_geometry import canonicalize, transform_primitives, adjacent
from four_side_1024.conflicts import ConflictIndex, _make_primitive, _exact_distance, _intersections
from four_side_1024.geometry import validate

R = 5.0


def build(routes, endpoints):
    built = {}
    for r in routes:
        if r['relation'] != 'adjacent':
            continue
        src = endpoints[r['source_endpoint']]; dst = endpoints[r['target_endpoint']]
        p, q, tr, kind = canonicalize(src['side'], dst['side'], src['routing_xy'], dst['routing_xy'])
        p = np.asarray(p); q = np.asarray(q)
        try:
            local = adjacent(p, q, float(q[1]), radius=R, width=.05)
            prim = transform_primitives(local, tr, inverse=True)
        except ValueError as exc:
            built[r['route_id']] = dict(state='error', why=str(exc), pair=r['pair'],
                                        src=r['source_endpoint'], dst=r['target_endpoint'],
                                        p=p.tolist(), q=q.tolist(), canon=(src['side'], dst['side']))
            continue
        built[r['route_id']] = dict(state='ok', prim=prim, pair=r['pair'],
                                    src=r['source_endpoint'], dst=r['target_endpoint'],
                                    canon=(src['side'], dst['side']),
                                    p=p.tolist(), q=q.tolist())
    return built


def conflict_partners(built, rid):
    me = built[rid]
    index = ConflictIndex(width=.05, gap=.125, sagitta=.0005)
    for other, rec in built.items():
        if other == rid or rec['state'] != 'ok':
            continue
        res = index.evaluate(me['prim'], exclude=None) if False else None
    # pair by pair using two-route index
    out = []
    for other, rec in built.items():
        if other == rid or rec['state'] != 'ok':
            continue
        pair_index = ConflictIndex(width=.05, gap=.125, sagitta=.0005)
        pair_index.add(other, rec['prim'])
        res = pair_index.evaluate(me['prim'])
        if not res['valid']:
            kinds = tuple(k for k in ('spacing_pairs', 'overlap_pairs', 'touch_pairs',
                                      'crossing_zone_overlap_pairs') if res.get(k))
            out.append((other, kinds))
    return out


def main():
    routes, endpoints, _, _ = load(DEFAULT_INPUT)
    built = build(routes, endpoints)
    ok = {k: v for k, v in built.items() if v['state'] == 'ok'}
    print('adjacent built ok:', len(ok), '/', len(built))
    # conflict degree
    deg = Counter()
    partners = {}
    for rid in ok:
        ps = conflict_partners(built, rid)
        partners[rid] = ps
        deg[len(ps)] += 1
    print('conflict-degree histogram:', dict(sorted(deg.items())))
    # classify pair direction combos
    combo = Counter()
    for rid, ps in partners.items():
        for other, kinds in ps:
            a = ok[rid]['canon']; b = ok[other]['canon']
            combo[(a, b, kinds)] += 1
    print('top conflicting direction pairs:')
    for key, cnt in combo.most_common(20):
        print('  ', key, cnt)
    # print detail for a few routes
    for rid in [513, 514, 769, 770, 712, 584]:
        if rid not in built:
            continue
        rec = built[rid]
        print('\nroute', rid, rec['pair'], rec['src'], '->', rec['dst'], 'canon', rec['canon'])
        print('  p,q canon', rec.get('p'), rec.get('q'))
        for other, kinds in partners.get(rid, [])[:8]:
            o = ok[other]
            print('   VS', other, o['pair'], o['src'], '->', o['dst'], o['canon'], kinds)
        if rid in partners:
            print('   total partners', len(partners[rid]))
    # distribution of |x difference| between partner route endpoints
    import json
    json.dump({str(k): [(int(o), list(map(str, ks))) for o, ks in v] for k, v in partners.items()},
              open(Path(__file__).with_name('direct_l_conflicts.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
