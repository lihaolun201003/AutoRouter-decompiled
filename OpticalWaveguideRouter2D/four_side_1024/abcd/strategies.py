"""ABCD experiment strategies for the four-side 1024-channel D56 study.

Only *how the 1024 identities are ordered / jointly selected* differs between the
algorithms; geometry, candidate families, clearance policy and budgets are the
same for every experiment.

* ``A`` opposite-first: NS -> EW -> EN -> ES -> SW -> NW (group order only).
* ``B`` adjacent-first: NW -> EN -> SW -> ES -> NS -> EW (historical best order,
  produces the preserved 467/1024 D56 result).
* ``C`` four-side round robin: every connection belongs to exactly one side (its
  source side); each turn takes ``batch`` routes from the current side's queue and
  then rotates N -> E -> S -> W (clockwise) or N -> W -> S -> E (counter-clockwise).
* ``D`` global joint optimisation lives in :mod:`four_side_1024.abcd.d_lns`.
"""
from __future__ import annotations

from collections import defaultdict

from ..d56.search import (LEGACY_GROUP_ORDER, OPPOSITE_FIRST_GROUP_ORDER,
                          _chord_length)

ALGORITHMS = ('A', 'B', 'C', 'D')

GROUP_ORDERS = {
    'A': list(OPPOSITE_FIRST_GROUP_ORDER),          # NS EW EN ES SW NW
    'B': ['NW', 'EN', 'SW', 'ES', 'NS', 'EW'],      # historical best (467/1024)
}

CLOCKWISE = ('N', 'E', 'S', 'W')
COUNTER_CLOCKWISE = ('N', 'W', 'S', 'E')

#: C design sweep grid (tested on V1, the winning design is then frozen and used
#: unchanged for both V1 and V2 as required by the contract).
C_SWEEP = tuple(
    dict(start_side=start, direction=direction, batch=batch,
         name=f'C_{direction}_{start}_b{batch}')
    for direction in ('cw', 'ccw')
    for start in ('N', 'E', 'S', 'W')
    for batch in (8, 32)
)


def _within_key(mode):
    if mode == 'x_desc':
        return lambda route, frame: (-frame.p[0],)
    if mode == 'x_asc':
        return lambda route, frame: (frame.p[0],)
    if mode == 'chord_desc':
        return lambda route, frame: (-_chord_length(frame),)
    if mode == 'chord_asc':
        return lambda route, frame: (_chord_length(frame),)
    if mode == 'csv':
        return lambda route, frame: (route['route_id'],)
    if mode == 'along_desc':
        return lambda route, frame: (-(frame.src_xy[0] if frame.source_side in 'NS'
                                       else frame.src_xy[1]), route['route_id'])
    if mode == 'along_asc':
        return lambda route, frame: ((frame.src_xy[0] if frame.source_side in 'NS'
                                      else frame.src_xy[1]), route['route_id'])
    raise ValueError('unknown within-group order: ' + mode)


def sequential_strategy(algorithm, within='x_desc', **extra):
    """Strategy dict consumed by :meth:`four_side_1024.d56.search.Router.run`."""
    if algorithm not in GROUP_ORDERS:
        raise ValueError('not a sequential algorithm: ' + str(algorithm))
    strategy = dict(name=f'{algorithm}_' + ('opposite_first' if algorithm == 'A'
                                            else 'adjacent_first'),
                    group_order=list(GROUP_ORDERS[algorithm]),
                    within_group=within,
                    dynamic_adjacent_order=False,
                    algorithm=algorithm)
    strategy.update(extra)
    return strategy


def owner_side(route):
    """Deterministic single owner side for every cross-side connection.

    The CSV only contains one direction per opposite pair (e.g. N->S but not S->N),
    so a pure "source side" split would leave S and W with adjacent-only queues of
    128 routes and N/E with 384.  Instead every connection is owned by one of the
    two sides it touches, alternating by route id:

    * opposite pair (256 routes) -> 128 to each of the two sides;
    * adjacent pair (128 routes) -> 64 to each of the two sides.

    Every side then owns exactly 256 connections mixing opposite-bound and
    adjacent-bound demands, and every connection is owned exactly once (a
    connection that touches two sides is never scheduled twice).
    """
    sides = (route['source_side'], route['target_side'])
    return sides[route['route_id'] % 2]


def round_robin_order(routes, frames, start_side='N', direction='cw', batch=16,
                      within='x_desc'):
    """Explicit C order: rotate through the four sides, ``batch`` routes each turn.

    Each connection is owned by exactly one side (:func:`owner_side`), so no
    connection can ever be scheduled twice even though it touches two sides.  Each
    side queue naturally contains both opposite-bound and adjacent-bound routes.
    """
    side_sequence = CLOCKWISE if direction == 'cw' else COUNTER_CLOCKWISE
    if start_side not in side_sequence:
        raise ValueError('unknown start side: ' + str(start_side))
    pivot = side_sequence.index(start_side)
    side_sequence = side_sequence[pivot:] + side_sequence[:pivot]
    queues = defaultdict(list)
    for route in routes:
        queues[owner_side(route)].append(route)
    key = _within_key(within)
    for side in list(queues):
        queues[side].sort(key=lambda route: key(route, frames[route['route_id']]))
    order = []
    cursor = {side: 0 for side in side_sequence}
    remaining = sum(len(queues[side]) for side in side_sequence)
    while remaining:
        for side in side_sequence:
            queue = queues[side]
            start = cursor[side]
            if start >= len(queue):
                continue
            stop = min(len(queue), start + batch)
            order.extend(route['route_id'] for route in queue[start:stop])
            remaining -= stop - start
            cursor[side] = stop
    return order


def describe(algorithm, **extra):
    info = dict(algorithm=algorithm, **extra)
    if algorithm in GROUP_ORDERS:
        info['group_order'] = list(GROUP_ORDERS[algorithm])
    return info
