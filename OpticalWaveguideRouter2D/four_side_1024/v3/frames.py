"""Canonical frames for the V3 mixed topology (same / opposite / adjacent).

Opposite and adjacent routes reuse the proven D56 canonical frames unchanged.
The new ``same`` frame maps the shared board edge to ``y = 0`` with inward +y:

* ``p = (sx, 0)`` -> ``q = (qx, 0)``, start direction +y, end direction **-y**
  (both ports on the same edge, the path leaves inward and comes back inward).

All four side mappings are rotations of the square (no reflection needed), so
distances, widths and radii are preserved exactly and the same candidate library
works for N/S/E/W.
"""
from __future__ import annotations

from ..d56.frames import RouteFrame, build_frames as _build_d56_frames
from ..legacy_geometry import canonicalize

#: world -> canonical transform for a same-side route, keyed by the shared side.
SAME_TRANSFORMS = {
    # S: identity (bottom edge, inward +y)
    'S': dict(matrix=[[1.0, 0.0], [0.0, 1.0]], offset=[0.0, 0.0]),
    # N: 180 degree rotation about the board centre
    'N': dict(matrix=[[-1.0, 0.0], [0.0, -1.0]], offset=[150.0, 150.0]),
    # E: rotate -90 degrees, (x, y) -> (y, 150 - x)
    'E': dict(matrix=[[0.0, 1.0], [-1.0, 0.0]], offset=[0.0, 150.0]),
    # W: rotate +90 degrees, (x, y) -> (150 - y, x)
    'W': dict(matrix=[[0.0, -1.0], [1.0, 0.0]], offset=[150.0, 0.0]),
}

START_DIR_SAME = (0.0, 1.0)
END_DIR_SAME = (0.0, -1.0)
START_DIR_OPPOSITE = (0.0, 1.0)
END_DIR_OPPOSITE = (0.0, 1.0)
START_DIR_ADJACENT = (0.0, 1.0)
END_DIR_ADJACENT = (1.0, 0.0)


def _apply(transform, point):
    matrix = transform['matrix']
    offset = transform['offset']
    return (matrix[0][0] * point[0] + matrix[0][1] * point[1] + offset[0],
            matrix[1][0] * point[0] + matrix[1][1] * point[1] + offset[1])


def canonicalize_same(side, source_point, target_point):
    """Return ``(p, q, transform, 'same')`` for a same-side route."""
    if side not in SAME_TRANSFORMS:
        raise ValueError(f'unknown side {side!r}')
    transform = dict(SAME_TRANSFORMS[side])
    transform.update(reflected=False, source_side=side, target_side=side)
    return (_apply(transform, source_point), _apply(transform, target_point),
            transform, 'same')


def build_frames(routes, endpoints):
    """Return ``{route_id: RouteFrame}`` for all V3 connections of one plane."""
    frames = {}
    for route in routes:
        src = endpoints[route['source_endpoint']]
        dst = endpoints[route['target_endpoint']]
        if route['relation'] == 'same':
            p, q, transform, kind = canonicalize_same(
                src['side'], src['routing_xy'], dst['routing_xy'])
        else:
            p, q, transform, kind = canonicalize(
                src['side'], dst['side'], src['routing_xy'], dst['routing_xy'])
            expected = 'opposite' if route['relation'] == 'opposite' else 'adjacent'
            if kind != expected:
                raise ValueError(f'route {route["route_id"]} frame kind {kind} != '
                                 f'relation {route["relation"]}')
        frames[route['route_id']] = RouteFrame(
            route['route_id'], kind, transform, p, q, src, dst,
            route['relation'], route['pair'])
    return frames


def start_end_dirs(frame):
    if frame.kind == 'same':
        return START_DIR_SAME, END_DIR_SAME
    if frame.kind == 'opposite':
        return START_DIR_OPPOSITE, END_DIR_OPPOSITE
    if frame.kind == 'adjacent':
        return START_DIR_ADJACENT, END_DIR_ADJACENT
    raise ValueError(f'unknown frame kind {frame.kind!r}')


# Re-export the pure D56 builder for V1/V2 compatibility tests.
build_d56_frames = _build_d56_frames
