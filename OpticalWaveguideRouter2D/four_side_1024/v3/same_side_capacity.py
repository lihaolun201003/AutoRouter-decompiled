"""Class-isolation capacity probe for V3: how many same-side / opposite / adjacent and
per-side (NN/SS/EE/WW) connections fit in one plane when routed ALONE.

This isolate-run separates "no geometry / candidate limit" from "interference with the
other classes".  It reuses the exact production router and strict index (candidate
budget 600 per route, same order strategies), so the numbers are directly comparable
to the mixed runs.

Writes ``outputs/four_side_1024_v3_huang_R40_gap30_abcd/feasibility/
same_side_capacity.json`` and a markdown table.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

from . import config as C
from . import frames as vframes
from . import ports, strategies
from .search import Router

OUT = C.OUTPUT_ROOT / 'feasibility'


def _isolate(plane_routes, plane_frames, route_ids, algorithm='B'):
    subset = [route for route in plane_routes if route['route_id'] in set(route_ids)]
    subset_frames = {route['route_id']: plane_frames[route['route_id']] for route in subset}
    router = Router(subset_frames, subset, cfg=dict(candidate_budget_per_route=600),
                    log=lambda message: None)
    spec = strategies.sequential_strategy(algorithm)
    order = strategies.build_order(subset, subset_frames, spec)
    started = time.perf_counter()
    for route_id in order:
        router._try_place(route_id)
    router.final_audit()
    reasons = Counter()
    for failure in router.failed.values():
        reasons.update(failure['rejection_counts'])
    families = Counter(accepted.family for accepted in router.accepted.values())
    return dict(total=len(subset), routed=len(router.accepted),
                failed=len(router.failed),
                evaluations=router.index.evaluations,
                seconds=round(time.perf_counter() - started, 1),
                families=dict(families),
                rejection_reasons=dict(reasons.most_common(6)))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    payload = dict(process=dict(radius_mm=C.RADIUS_MM, width_mm=C.WIDTH_MM,
                                edge_gap_mm=C.EDGE_GAP_MM,
                                clearance_mm=C.CLEARANCE_MM, board_mm=C.BOARD_MM),
                   note='each subset is routed ALONE in the plane with the same router, '
                        'strict index and candidate library as the mixed runs',
                   planes={})
    for plane in C.PLANES:
        routes, endpoints, _connectors, _validation = ports.load_plane(plane)
        frame_map = vframes.build_frames(routes, endpoints)
        record = dict(relations={}, same_sides={})
        for relation in C.RELATIONS:
            ids = [route['route_id'] for route in routes if route['relation'] == relation]
            record['relations'][relation] = _isolate(routes, frame_map, ids)
        for side in 'NESW':
            ids = [route['route_id'] for route in routes
                   if route['pair'] == side * 2]
            record['same_sides'][side] = _isolate(routes, frame_map, ids)
        payload['planes'][plane] = record
        print(plane, 'relations:',
              {relation: record['relations'][relation]['routed']
               for relation in C.RELATIONS},
              'same sides:',
              {side: record['same_sides'][side]['routed'] for side in 'NESW'},
              flush=True)
    (OUT / 'same_side_capacity.json').write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    lines = ['# V3 class isolation capacity (single-class routing in one plane)', '',
             'Each subset is routed alone with the production router and the same strict '
             'index; compare with the mixed-class runs to separate geometry limits from '
             'interference.', '',
             '| plane | same alone | opposite alone | adjacent alone | NN alone | SS alone '
             '| EE alone | WW alone |', '|---|---:|---:|---:|---:|---:|---:|---:|']
    for plane, record in payload['planes'].items():
        relations = record['relations']
        sides = record['same_sides']
        lines.append(
            f"| {plane} | {relations['same']['routed']}/{relations['same']['total']} | "
            f"{relations['opposite']['routed']}/{relations['opposite']['total']} | "
            f"{relations['adjacent']['routed']}/{relations['adjacent']['total']} | "
            + ' | '.join(f"{sides[side]['routed']}/{sides[side]['total']}"
                         for side in 'NESW') + ' |')
    (OUT / 'same_side_capacity.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('written', OUT / 'same_side_capacity.json')


if __name__ == '__main__':
    main()
