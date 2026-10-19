"""V3 scheduling strategies A/B/C for the mixed same/opposite/adjacent topology.

* A opposite-first: ``NS, EW`` -> same-side ``NN, SS, EE, WW`` -> adjacent
* B same-first: same-side -> adjacent -> opposite (tests whether reserving the
  U/refold tracks near the edges reduces the later congestion)
* C four-side round-robin: every side owns 256 connections mixing all three classes;
  small batches are interleaved by side.

Within a same-side group the wider connection (larger |dx|) is placed first: its U is
the outermost arch of the nesting, which leaves the shallower tracks for the nested
inner connections.  All strategies are pure ordering; they do not change geometry and
are followed by the same transactional rip-up.
"""
from __future__ import annotations

from collections import defaultdict

SIDES = ('N', 'E', 'S', 'W')
SAME_PAIRS = ('NN', 'SS', 'EE', 'WW')
ADJACENT_PAIRS = ('NE', 'NW', 'ES', 'SW')
OPPOSITE_PAIRS = ('NS', 'EW')

GROUP_ORDERS = {
    'A': OPPOSITE_PAIRS + SAME_PAIRS + ADJACENT_PAIRS,
    'B': SAME_PAIRS + ADJACENT_PAIRS + OPPOSITE_PAIRS,
}


def _sort_key(mode, frame):
    """Ordering inside one group (frames share the relation/kind)."""
    if mode == 'span_desc':
        return (-abs(frame.dx), -min(frame.p[0], frame.q[0]), frame.route_id)
    if mode == 'span_asc':
        # nested same-side arches: the narrow inner connection is placed first at the
        # shallowest track, the enclosing wider one later on a deeper track, which is
        # the only nesting order that does not create double crossings.
        return (abs(frame.dx), min(frame.p[0], frame.q[0]), frame.route_id)
    if mode == 'x_desc':
        return (-frame.p[0], -abs(frame.dx), frame.route_id)
    return (frame.route_id,)


def sequential_strategy(algorithm, within=None):
    if algorithm not in GROUP_ORDERS:
        raise ValueError(algorithm)
    if algorithm == 'A':
        groups = GROUP_ORDERS['A']
        name = 'A_opposite_first'
        default_within = 'x_desc'
    else:
        groups = GROUP_ORDERS['B']
        name = 'B_same_first'
        default_within = 'span_asc'
    return dict(name=name, algorithm=algorithm, groups=list(groups),
                within=within or default_within,
                description=('opposite -> same -> adjacent' if algorithm == 'A'
                             else 'same -> adjacent -> opposite'))


def build_order(routes, frames, spec):
    by_pair = defaultdict(list)
    for route in routes:
        by_pair[route['pair']].append(route['route_id'])
    order = []
    for pair in spec['groups']:
        if pair in SAME_PAIRS:
            mode = 'span_asc'
        else:
            mode = spec['within']
        ids = sorted(by_pair.get(pair, []),
                     key=lambda rid: _sort_key(mode, frames[rid]))
        order.extend(ids)
    expected = {route['route_id'] for route in routes}
    if set(order) != expected or len(order) != len(expected):
        raise ValueError('sequential order must contain every route exactly once')
    return order


def round_robin_spec(start_side='N', direction='cw', batch=16):
    if start_side not in SIDES:
        raise ValueError(start_side)
    if direction not in ('cw', 'ccw'):
        raise ValueError(direction)
    return dict(name='C_round_robin', algorithm='C',
                start_side=start_side, direction=direction, batch=batch,
                description='four-side round robin, every side mixes all three classes')


def _side_cycle(start_side, direction):
    index = SIDES.index(start_side)
    cycle = list(SIDES[index:]) + list(SIDES[:index])
    if direction == 'ccw':
        cycle = [cycle[0]] + list(reversed(cycle[1:]))
    return cycle


def round_robin_order(routes, frames, spec):
    """Interleave connections by side and by class inside every side queue."""
    cycle = _side_cycle(spec['start_side'], spec['direction'])
    batch = int(spec['batch'])
    per_class = max(1, batch // 3)
    queues = {side: {relation: [] for relation in ('same', 'opposite', 'adjacent')}
              for side in SIDES}
    for route in routes:
        queues[route['source_side']][route['relation']].append(route['route_id'])
    for side in SIDES:
        for relation, ids in queues[side].items():
            ids.sort(key=lambda rid: _sort_key('span_asc' if relation == 'same'
                                               else 'x_desc', frames[rid]))
    order = []
    while any(any(ids for ids in queues[side].values()) for side in cycle):
        progressed = False
        for side in cycle:
            for relation in ('same', 'opposite', 'adjacent'):
                ids = queues[side][relation]
                if not ids:
                    continue
                take = ids[:per_class]
                order.extend(take)
                del ids[:len(take)]
                progressed = True
        if not progressed:
            break
    expected = {route['route_id'] for route in routes}
    if set(order) != expected or len(order) != len(expected):
        missing = expected - set(order)
        raise ValueError(f'round-robin order incomplete: {len(missing)} missing')
    return order


def describe(algorithm, **extra):
    if algorithm == 'C':
        return round_robin_spec(**extra)
    return sequential_strategy(algorithm, **extra)
