"""Layout state of one new-connectivity plane.

Reuses the frozen :class:`four_side_1024.v2opt.core.LayoutState` (same D56 exact
index, same oracles, same acceptance rules).  The only difference to the V3-C4
state is the route source:

* routes/endpoints come from the new combined connectivity table;
* connections whose two ports are on the *same* board side have no canonical
  D56 frame in the frozen geometry module (it requires two distinct sides), so
  they are routed with the existing R15 same-side U-turn family
  (``four_side_1024.r15.u_geometry``) and only contribute their forced endpoint
  stems to the static occupancy.
"""
from __future__ import annotations

from ..d56.frames import build_frames
from ..d56.search import static_endpoint_lines
from ..fslw import config as C
from ..v2opt.core import LayoutState, new_index, router_cfg
from . import connectivity as CONN


class _SameSideStub:
    """Minimal frame stand-in for static endpoint stems of same-side routes."""

    __slots__ = ('route_id', 'source_side', 'target_side', 'src_xy', 'dst_xy', 'kind')

    def __init__(self, route, endpoints):
        self.route_id = route['route_id']
        self.source_side = route['source_side']
        self.target_side = route['target_side']
        self.src_xy = tuple(float(v) for v in
                            endpoints[route['source_endpoint']]['routing_xy'])
        self.dst_xy = tuple(float(v) for v in
                            endpoints[route['target_endpoint']]['routing_xy'])
        self.kind = 'same'


class ManualLayoutState(LayoutState):
    """One z plane of the new manual connectivity, frozen layout engine unchanged."""

    def __init__(self, plane, cfg=None, log=print):
        self.topology = CONN.TOPOLOGY
        self.plane = plane
        self.cfg = router_cfg()
        if cfg:
            self.cfg.update(cfg)
        self.log = log
        self.routes, self.endpoints, self.connectors, self.validation = \
            CONN.load_plane(plane)
        self.route_by_id = {route['route_id']: route for route in self.routes}
        normal = [route for route in self.routes if route['relation'] != 'same']
        same = [route for route in self.routes if route['relation'] == 'same']
        self.normal_routes = normal
        self.same_side_routes = same
        self.frames = build_frames(normal, self.endpoints)
        stubs = {route['route_id']: _SameSideStub(route, self.endpoints)
                 for route in same}
        static_frames = dict(self.frames)
        static_frames.update(stubs)
        self.static_h, self.static_v = static_endpoint_lines(static_frames)
        from ..fslw.candidates import FrameOracleSet
        self.oracles = FrameOracleSet(self.frames, self.static_h, self.static_v,
                                      clearance=C.CLEARANCE_MM)
        self.index = new_index(self.cfg)
        self.accepted = {}
        self.failed = {}
        self.source = dict(topology=CONN.TOPOLOGY,
                           connectivity=str(CONN.COMBINED_CSV),
                           connectivity_sha256=self.validation['csv_sha256'],
                           plane=plane)


def state_for(plane, cfg=None, log=print):
    return ManualLayoutState(plane, cfg=cfg, log=log)
