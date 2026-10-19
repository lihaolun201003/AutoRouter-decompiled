"""Canonical D56 routing frames for the four-side 1024 layout.

Every route is mapped by a rigid rotation/reflection into one of two canonical
frames (the same frames the reverse-engineered AutoRouter uses):

* ``opposite``  p = (sx, 0) travelling +y, q = (tx, 150) travelling +y
* ``adjacent``  p = (sx, 0) travelling +y, q = (150, qy) travelling +x

Reflections are allowed because the D56 path families are mirror symmetric and
the physical model is isotropic; the CSV identity, endpoint coordinates and
port directions are never changed.  ``transform_primitives(..., inverse=True)``
maps canonical geometry back to global millimetres.
"""
from __future__ import annotations

from ..legacy_geometry import canonicalize, transform_primitives


class RouteFrame:
    """Static per-route canonical frame (matrix/offset, kind, canonical poses)."""

    __slots__ = ('route_id', 'kind', 'matrix', 'offset', 'transform', 'p', 'q',
                 'source_side', 'target_side', 'relation', 'pair',
                 'src_xy', 'dst_xy', 'src_inward', 'dst_inward')

    def __init__(self, route_id, kind, transform, p, q, src, dst, relation, pair):
        self.route_id = route_id
        self.kind = kind
        self.transform = transform
        self.matrix = transform['matrix']
        self.offset = transform['offset']
        self.p = (float(p[0]), float(p[1]))
        self.q = (float(q[0]), float(q[1]))
        self.source_side = src['side']
        self.target_side = dst['side']
        self.relation = relation
        self.pair = pair
        self.src_xy = tuple(map(float, src['routing_xy']))
        self.dst_xy = tuple(map(float, dst['routing_xy']))
        self.src_inward = tuple(map(float, src['inward']))
        self.dst_inward = tuple(map(float, dst['inward']))

    # -- canonical <-> world ------------------------------------------------
    def to_world(self, primitives):
        return transform_primitives(primitives, self.transform, inverse=True)

    def to_canonical(self, primitives):
        return transform_primitives(primitives, self.transform, inverse=False)

    @property
    def dx(self):
        return self.q[0] - self.p[0]

    @property
    def qy(self):
        return self.q[1]

    def __repr__(self):
        return (f'RouteFrame({self.route_id}, {self.kind}, '
                f'{self.source_side}->{self.target_side}, p={self.p}, q={self.q})')


def build_frames(routes, endpoints):
    """Return ``{route_id: RouteFrame}`` for all 1024 identities."""
    frames = {}
    for r in routes:
        src = endpoints[r['source_endpoint']]
        dst = endpoints[r['target_endpoint']]
        p, q, transform, kind = canonicalize(src['side'], dst['side'],
                                             src['routing_xy'], dst['routing_xy'])
        frames[r['route_id']] = RouteFrame(r['route_id'], kind, transform, p, q,
                                           src, dst, r['relation'], r['pair'])
    return frames
