"""Try several known ordering strategies for pure-90 z2 routing (comparable budget).

Each order is a fresh sequential routing pass; results (routed count + checkpoint)
are recorded so the best order can be continued with R&R.  Runs one order in this
process; call with --order NAME in separate processes for parallelism.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(r'C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter2D')
sys.path.insert(0, str(ROOT))

from four_side_1024.abcd import strategies as A  # noqa: E402
from four_side_1024.d56.search import build_order  # noqa: E402
from four_side_1024.v2opt import search as S  # noqa: E402
from four_side_1024.v2opt.core import LayoutState  # noqa: E402

OUT = ROOT / 'outputs/four_side_1024_v2_ortho90_v01'
ORDERS = ('csv', 'csv_desc', 'group_ensw', 'group_swesnw',
          'round_robin_N_cw', 'round_robin_E_ccw', 'global_congestion', 'global_length')


def build_order_for(name, state):
    routes, frames = state.routes, state.frames
    if name == 'csv':
        return [route['route_id'] for route in routes]
    if name == 'csv_desc':
        return [route['route_id'] for route in reversed(routes)]
    if name.startswith('group_'):
        group = {'group_ensw': ['EN', 'ES', 'SW', 'NW'],
                 'group_swesnw': ['SW', 'ES', 'NW', 'EN']}[name]
        strategy = dict(name=name, group_order=group, within_group='x_desc')
        return build_order(routes, frames, strategy)
    if name.startswith('round_robin_'):
        _, _, start, direction = name.split('_')
        return A.round_robin_order(routes, frames, start_side=start,
                                   direction=direction, batch=32, within='x_desc')
    if name == 'global_congestion':
        from four_side_1024.d56.search import static_congestion
        state.congestion = static_congestion(state.routes, None, state.frames)
        strategy = dict(name='global_dynamic', global_key='congestion_desc')
        return build_order(routes, frames, strategy, congestion=state.congestion)
    if name == 'global_length':
        strategy = dict(name='global_dynamic', global_key='length_desc')
        return build_order(routes, frames, strategy)
    raise ValueError(name)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plane', default='z2')
    parser.add_argument('--order', required=True, choices=ORDERS)
    parser.add_argument('--budget', type=int, default=1600)
    args = parser.parse_args(argv)
    state = LayoutState('V2', args.plane)
    order = build_order_for(args.order, state)
    started = time.perf_counter()
    details, summary = S.sequential_commit(state, order, budget=args.budget,
                                           geometry_mode='ortho90')
    out = OUT / 'experiments' / 'order_sweep'
    out.mkdir(parents=True, exist_ok=True)
    checkpoint = OUT / 'checkpoints' / f'order_{args.order}_{args.plane}.json'
    state.save_checkpoint(checkpoint, tag=f'order_{args.order}')
    payload = dict(order=args.order, plane=args.plane, budget=args.budget,
                   routed=len(state.accepted), seconds=time.perf_counter() - started,
                   summary=summary,
                   applied_route_ids=summary.get('applied_route_ids'),
                   checkpoint=str(checkpoint),
                   failure_reasons={})
    from collections import Counter
    payload['failure_reasons'] = dict(Counter(
        failure.get('reason') for failure in state.failed.values()))
    (out / f'order_{args.order}_{args.plane}.json').write_text(
        json.dumps(payload, indent=1, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({key: payload[key] for key in
                      ('order', 'plane', 'routed', 'seconds')}, ensure_ascii=False))
    return payload


if __name__ == '__main__':
    main()
