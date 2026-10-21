"""V3-C4 layout state: the frozen v2opt.LayoutState wired to the V3 CSV loader."""
from __future__ import annotations

from ..d56.frames import build_frames
from ..d56.search import static_endpoint_lines
from ..fslw import config as C
from ..v2opt.core import LayoutState, new_index, router_cfg
from . import inputs as V3


class V3LayoutState(LayoutState):
    """One z plane of the V3-C4 topology, with the unchanged layout engine."""

    def __init__(self, topology=V3.TOPOLOGY, plane='z1', cfg=None, log=print):
        self.topology = topology
        self.plane = plane
        self.cfg = router_cfg()
        if cfg:
            self.cfg.update(cfg)
        self.log = log
        self.routes, self.endpoints, self.connectors, self.validation = \
            V3.load_plane(plane)
        self.route_by_id = {route['route_id']: route for route in self.routes}
        self.frames = build_frames(self.routes, self.endpoints)
        self.static_h, self.static_v = static_endpoint_lines(self.frames)
        from ..fslw.candidates import FrameOracleSet
        self.oracles = FrameOracleSet(self.frames, self.static_h, self.static_v,
                                      clearance=C.CLEARANCE_MM)
        self.index = new_index(self.cfg)
        self.accepted = {}
        self.failed = {}
        self.source = {}

    @classmethod
    def from_history(cls, topology, plane, routes_path, cfg=None, log=print):
        state = cls(topology, plane, cfg=cfg, log=log)
        import json
        from pathlib import Path
        payload = json.loads(Path(routes_path).read_text(encoding='utf-8'))
        records = payload.get('routes') or payload
        loaded, failed = state.load_records(records)
        state.source = dict(history=str(routes_path),
                            history_schema=payload.get('schema'),
                            history_algorithm=payload.get('algorithm'),
                            history_experiment=payload.get('experiment'),
                            loaded=loaded, failed_records=failed)
        return state


def state_for(plane, cfg=None, log=print):
    return V3LayoutState(V3.TOPOLOGY, plane, cfg=cfg, log=log)
