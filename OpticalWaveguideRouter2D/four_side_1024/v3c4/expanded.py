"""Expanded R15 planar candidate families for the remaining hard C4 groups.

Existing ``v2opt.candext`` families are local (L / Z3 / TURN_S / ...); the
remaining z2 corner groups need a *global detour*: leave the port, travel to the
empty part of the board, turn around and approach the second port along its fixed
tangent.  The detour below is built with the same R15 quarter-arc geometry as the
frozen router (``fslw.geom.staircase``) and is validated by the same exact
D56Index at insertion time; nothing is relaxed.
"""
from __future__ import annotations

import itertools

from ..fslw import config as C
from ..fslw import geom


def _staircase(vertices, start_dir, end_dir):
    primitives = geom.staircase(vertices, start_dir, end_dir,
                                radius=float(C.RADIUS_MM),
                                width=float(C.WIDTH_MM))
    return primitives


def detour_adjacent(frame, levels=(1, 2, 3)):
    """Global detour candidates for adjacent frames with a short terminal leg.

    Canonical adjacent frame: ``p=(sx,0)`` travelling +y, ``q=(150,qy)`` travelling +x.
    A direct L needs both legs >= R; for the corner groups ``qy < R`` and the
    direct/短-S families fail.  The detour travels west into the free board area,
    then returns east and approaches ``q`` along its fixed +x tangent.
    """
    p = (float(frame.p[0]), float(frame.p[1]))
    q = (float(frame.q[0]), float(frame.q[1]))
    qy = q[1]
    sx = p[0]
    if qy >= 2.0 * C.RADIUS_MM or sx <= C.BOARD_MM - 2.0 * C.RADIUS_MM:
        # only needed for the short terminal-leg corner case
        return
    y1_grid = {1: (60.0, 90.0), 2: (45.0, 75.0, 105.0), 3: (35.0, 55.0, 70.0, 85.0, 100.0, 115.0)}
    x2_grid = {1: (30.0, 60.0), 2: (20.0, 45.0, 75.0), 3: (15.0, 35.0, 55.0, 70.0, 90.0)}
    for level in levels:
        for y1 in y1_grid[level]:
            if y1 <= C.RADIUS_MM + 2.0:
                continue
            for x2 in x2_grid[level]:
                if sx - x2 < 2.0 * C.RADIUS_MM:
                    continue
                for y2 in (40.0, 55.0, 70.0, 85.0, 100.0):
                    if y2 >= y1 - C.RADIUS_MM - 2.0 or y2 <= qy + C.RADIUS_MM + 2.0:
                        continue
                    for x3 in (130.0, 131.0, 129.0, 132.0):
                        if x3 <= x2 + C.RADIUS_MM:
                            continue
                        if x3 + C.RADIUS_MM <= sx:
                            # final horizontal would cross the initial vertical leg
                            continue
                        if x3 + C.RADIUS_MM >= C.BOARD_MM - 1.0:
                            continue
                        vertices = [p, (sx, y1), (x2, y1), (x2, y2), (x3, y2),
                                    (x3, qy), q]
                        primitives = _staircase(vertices, (0.0, 1.0), (1.0, 0.0))
                        if primitives is not None:
                            yield dict(family='DETOUR',
                                       params=dict(y1=y1, x2=x2, y2=y2, x3=x3),
                                       primitives=primitives)


def detour_opposite(frame, levels=(1, 2)):
    """Global detour candidates for opposite frames with a very small lateral shift.

    Canonical opposite frame: ``p=(sx,0)`` travelling +y, ``q=(tx,150)`` travelling +y.
    The detour goes sideways into the free area, travels up, then returns to the
    target ``tx`` and enters the port vertically.
    """
    p = (float(frame.p[0]), float(frame.p[1]))
    q = (float(frame.q[0]), float(frame.q[1]))
    sx, tx = p[0], q[0]
    for level in levels:
        for x2 in ((30.0, 60.0) if level == 1 else (20.0, 45.0, 75.0, 105.0)):
            if abs(x2 - sx) < 2.0 * C.RADIUS_MM:
                continue
            if abs(x2 - tx) < 2.0 * C.RADIUS_MM:
                continue
            for y1 in (40.0, 60.0, 80.0, 100.0):
                if y1 < 2.0 * C.RADIUS_MM:
                    continue
                vertices = [p, (sx, y1), (x2, y1), (x2, 150.0 - y1),
                            (tx, 150.0 - y1), q]
                primitives = _staircase(vertices, (0.0, 1.0), (0.0, 1.0))
                if primitives is not None:
                    yield dict(family='DETOUR_OPP',
                               params=dict(x2=x2, y1=y1), primitives=primitives)


def expanded_candidates(frame, oracle, use=('candext', 'ortho90', 'detour'),
                        levels=(1, 2, 3)):
    """Yield candidates from the frozen generators plus the new detour families."""
    from ..v2opt import candext
    from ..v2opt import ortho90

    if 'candext' in use:
        if frame.kind == 'opposite':
            yield from candext.candidates_opposite(frame, oracle)
        else:
            yield from candext.candidates_adjacent(frame, oracle)
    if 'ortho90' in use:
        generator = ortho90.Ortho90Generator(seed=20261019)
        yield from generator.candidates(frame, oracle)
    if 'detour' in use:
        if frame.kind == 'adjacent':
            yield from detour_adjacent(frame, levels=levels)
        else:
            yield from detour_opposite(frame, levels=levels)
