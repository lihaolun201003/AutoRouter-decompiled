"""Live geometry state of one height plane plus fslw-compatible artefact export.

The state is *reconstructed from real primitives*, never from route ids: every
routed record of a historical ``routes.json`` is parsed into D56 primitives,
prepared for the exact single-layer index and registered in the canonical-frame
occupancy oracles.  ``LayoutState.verify()`` then re-audits the reconstructed
layout with the exact index and compares the record identity fields against the
V2 CSV, which is the load-safety requirement of the task.
"""
from __future__ import annotations

import copy
import datetime
import json
import math
import time
from pathlib import Path

from ..d56.frames import build_frames
from ..d56.index import D56Index, prepare
from ..d56.search import RouteResult, static_endpoint_lines
from ..fslw import config as C
from ..fslw import ports
from . import config as V

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / 'outputs/four_side_1024_v2_candidate_rr_v01'
IDENTITY_FIELDS = ('relation', 'pair', 'source_side', 'target_side',
                   'source_row', 'target_row', 'source_endpoint', 'target_endpoint')


def iso_now():
    return datetime.datetime.now(
        datetime.timezone(datetime.timedelta(hours=8))).isoformat()


def router_cfg(**overrides):
    """D56 index settings - physical parameters are the frozen fslw ones."""
    cfg = dict(width=C.WIDTH_MM, gap=C.EDGE_GAP_MM, sagitta=C.SAGITTA_MM,
               min_radius_mm=C.RADIUS_MM,
               min_cross_angle_deg=C.MIN_CROSS_ANGLE_DEG,
               crossing_policy='strict')
    cfg.update(overrides)
    return cfg


def new_index(cfg):
    return D56Index(width=cfg['width'], gap=cfg['gap'], sagitta=cfg['sagitta'],
                    min_cross_angle_deg=cfg['min_cross_angle_deg'],
                    crossing_policy=cfg['crossing_policy'])


class LayoutState:
    """One plane: routes, frames, exact index, oracles and accepted geometry."""

    def __init__(self, topology, plane, cfg=None, log=print):
        self.topology = topology
        self.plane = plane
        self.cfg = router_cfg()
        if cfg:
            self.cfg.update(cfg)
        self.log = log
        self.routes, self.endpoints, self.connectors, self.validation = \
            ports.load_plane(topology, plane)
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

    # -- construction ------------------------------------------------------
    @classmethod
    def from_history(cls, topology, plane, routes_path, cfg=None, log=print):
        state = cls(topology, plane, cfg=cfg, log=log)
        path = Path(routes_path)
        payload = json.loads(path.read_text(encoding='utf-8'))
        records = payload.get('routes') or payload
        loaded, failed = state.load_records(records)
        state.source = dict(history=str(path), history_schema=payload.get('schema'),
                            history_algorithm=payload.get('algorithm'),
                            history_experiment=payload.get('experiment'),
                            loaded=loaded, failed_records=failed)
        log(f'{plane}: loaded {loaded} historical routes from {path.name} '
            f'({failed} failed records kept)')
        return state

    def load_records(self, records):
        """Reconstruct accepted geometry from real primitive chains."""
        loaded = 0
        failed = 0
        for record in records:
            route_id = int(record['route_id'])
            if record.get('status') == 'routed':
                primitives = record.get('primitives')
                if not primitives:
                    raise ValueError(f'route {route_id}: routed record without primitives')
                prepared = prepare(primitives)
                frame = self.frames[route_id]
                result = RouteResult(
                    route_id, (record.get('candidate') or {}).get('family'),
                    (record.get('candidate') or {}).get('params') or {},
                    primitives, prepared, prepared.length,
                    primitives_crossings(record), 0,
                    prepared.bend_count)
                self.accepted[route_id] = result
                self.index.add(route_id, prepared)
                self.oracles.add(route_id, prepared)
                loaded += 1
            else:
                self.failed[route_id] = dict(
                    route_id=route_id,
                    reason=record.get('reason') or 'not_attempted',
                    evaluated=int(record.get('evaluated') or 0),
                    rejection_counts=dict(record.get('rejection_counts') or {}),
                    blockers=dict(record.get('blockers') or {}),
                    stale=True)
                failed += 1
        return loaded, failed

    # -- geometry maintenance ---------------------------------------------
    def add(self, result):
        self.accepted[result.route_id] = result
        self.failed.pop(result.route_id, None)
        self.index.add(result.route_id, result.prepared)
        self.oracles.add(result.route_id, result.prepared)

    def remove(self, route_id):
        self.accepted.pop(route_id, None)
        self.index.remove(route_id)
        self.oracles.remove(route_id)

    def oracle_for(self, route_id):
        return self.oracles.oracle_for(self.frames[route_id])

    def rebuild(self, accepted=None, failed=None):
        """Rebuild the exact index/oracles from a dict of RouteResults."""
        if accepted is not None:
            self.accepted = dict(accepted)
        if failed is not None:
            self.failed = dict(failed)
        self.index = new_index(self.cfg)
        from ..fslw.candidates import FrameOracleSet
        self.oracles = FrameOracleSet(self.frames, self.static_h, self.static_v,
                                      clearance=C.CLEARANCE_MM)
        for route_id, result in self.accepted.items():
            self.index.add(route_id, result.prepared)
            self.oracles.add(route_id, result.prepared)

    def snapshot(self):
        return dict(accepted=dict(self.accepted), failed=copy.deepcopy(self.failed))

    def restore(self, snapshot):
        self.rebuild(accepted=snapshot['accepted'], failed=snapshot['failed'])

    # -- verification ------------------------------------------------------
    def verify(self, verbose=False):
        """Exact internal re-audit of the reconstructed layout."""
        audit = new_index(self.cfg)
        for route_id, result in self.accepted.items():
            audit.add(route_id, result.prepared)
        bad = []
        for route_id, result in self.accepted.items():
            evaluation = audit.evaluate(result.prepared, exclude=[route_id])
            if not evaluation.valid:
                bad.append(dict(route_id=route_id, reason=evaluation.reason,
                                blockers=list(evaluation.blockers)[:5]))
        identity_errors = []
        for record in self.routes:
            route_id = record['route_id']
            accepted = route_id in self.accepted
            failed = route_id in self.failed
            if accepted == failed:
                identity_errors.append(f'route {route_id} status ambiguous')
                continue
            result = self.accepted.get(route_id)
            if result is not None:
                first = result.primitives[0]
                last = result.primitives[-1]
                start = tuple(round(float(v), 6) for v in first['p0'])
                end = tuple(round(float(v), 6) for v in last['p1'])
                source = tuple(round(float(v), 6) for v in
                               self.endpoints[record['source_endpoint']]['routing_xy'])
                target = tuple(round(float(v), 6) for v in
                               self.endpoints[record['target_endpoint']]['routing_xy'])
                if start != source or end != target:
                    identity_errors.append(
                        f'route {route_id} endpoint mismatch {start}/{source} '
                        f'{end}/{target}')
        info = dict(plane=self.plane, routed=len(self.accepted),
                    failed=len(self.failed), index_routes=len(self.index),
                    invalid=bad, identity_errors=identity_errors[:20],
                    identity_error_count=len(identity_errors),
                    audit_passed=(not bad and not identity_errors))
        if verbose:
            self.log(f'{self.plane}: verify routed={info["routed"]} '
                     f'invalid={len(bad)} identity_errors={len(identity_errors)}')
        return info

    # -- search helpers -----------------------------------------------------
    def failure_blockers(self, route_id, limit=None, applied_only=True):
        failure = self.failed.get(route_id) or {}
        counts = failure.get('blockers') or {}
        pairs = []
        for key, count in counts.items():
            blocker = int(key)
            if applied_only and blocker not in self.accepted:
                continue
            pairs.append((blocker, int(count)))
        pairs.sort(key=lambda item: -item[1])
        if limit is not None:
            pairs = pairs[:limit]
        return [blocker for blocker, _count in pairs]

    def blocker_frequency(self, route_ids=None):
        counts = {}
        for route_id in (route_ids if route_ids is not None else self.failed):
            for key, count in (self.failed.get(route_id, {}).get('blockers') or {}).items():
                blocker = int(key)
                if blocker in self.accepted:
                    counts[blocker] = counts.get(blocker, 0) + int(count)
        return dict(sorted(counts.items(), key=lambda item: -item[1]))

    # -- export ------------------------------------------------------------
    def route_record(self, route_id, strategy_label):
        route = self.route_by_id[route_id]
        result = self.accepted.get(route_id)
        base = dict(route_id=route_id, plane=route['plane'], z_mm=route['z_mm'],
                    relation=route['relation'], pair=route['pair'],
                    source_side=route['source_side'], target_side=route['target_side'],
                    source_row=route['source_row'], target_row=route['target_row'],
                    source_endpoint=route['source_endpoint'],
                    target_endpoint=route['target_endpoint'])
        if result is None:
            failure = self.failed.get(route_id, {})
            base.update(status='failed', reason=failure.get('reason', 'not_attempted'),
                        evaluated=failure.get('evaluated', 0),
                        rejection_counts=failure.get('rejection_counts', {}),
                        blockers=failure.get('blockers', {}))
            return base
        return dict(base, status='routed', layer=0,
                    length_mm=result.length_mm, length_cm=result.length_mm / 10.0,
                    propagation_loss_db=(C.PROPAGATION_LOSS_DB_PER_CM
                                         * result.length_mm / 10.0),
                    bend_count=result.bends, primitives=result.primitives,
                    candidate=dict(family=result.family, params=result.params,
                                   strategy=strategy_label,
                                   index=result.candidate_index))

    def payload(self, algorithm, algorithm_detail, strategy_label):
        routed_records = sum(1 for route in self.routes
                             if route['route_id'] in self.accepted)
        records = [self.route_record(route['route_id'], strategy_label)
                   for route in self.routes]
        process = C.process_record()
        return dict(
            schema='four_side_1024_fslw_plane_routes_v1', units='mm', layer=0,
            experiment=f'{self.topology}_{algorithm}_{self.plane}',
            topology=self.topology, algorithm=algorithm, plane=self.plane,
            z_mm=C.PLANE_Z_MM[C.PLANE_ROW[self.plane]],
            port_model=C.PORT_MODEL, endpoint_mode='real_2x16_dual_height',
            csv_sha256=self.validation['csv_sha256'],
            csv_path=self.validation['csv_path'], process=process,
            algorithm_detail=algorithm_detail,
            plane_validation=self.validation,
            statistics=dict(routed=routed_records,
                            failed=len(self.routes) - routed_records,
                            source=self.source),
            routes=records)

    def write_plane(self, out_dir, algorithm, algorithm_detail, strategy_label,
                    extra=None):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = self.payload(algorithm, algorithm_detail, strategy_label)
        if extra:
            payload['v2opt'] = extra
        tmp = out_dir / 'routes.json.tmp'
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        tmp.replace(out_dir / 'routes.json')
        failed = [record for record in payload['routes']
                  if record['status'] != 'routed']
        (out_dir / 'failed_routes.json').write_text(
            json.dumps(dict(experiment=payload['experiment'],
                            failed_routes=failed), ensure_ascii=False),
            encoding='utf-8')
        config_record = dict(experiment=payload['experiment'], topology=self.topology,
                             algorithm=algorithm, plane=self.plane,
                             z_mm=payload['z_mm'], port_model=C.PORT_MODEL,
                             process=payload['process'],
                             algorithm_detail=algorithm_detail,
                             routed=payload['statistics']['routed'],
                             failed=payload['statistics']['failed'])
        (out_dir / 'config.json').write_text(
            json.dumps(config_record, indent=1, ensure_ascii=False), encoding='utf-8')
        (out_dir / 'CHECKPOINT.json').write_text(json.dumps(dict(
            experiment=payload['experiment'], status='complete', timestamp=iso_now(),
            routed=payload['statistics']['routed'],
            total=len(self.routes),
            source=self.source), indent=1, ensure_ascii=False), encoding='utf-8')
        return out_dir

    def dump(self):
        """JSON-serialisable layout (used to hand geometry to worker processes)."""
        return dict(schema='four_side_1024_v2opt_layout_dump_v1',
                    topology=self.topology, plane=self.plane,
                    routed=[dict(route_id=route_id, primitives=result.primitives,
                                 family=result.family, params=result.params)
                            for route_id, result in sorted(self.accepted.items())],
                    failed={str(route_id): failure for route_id, failure
                            in self.failed.items()})

    @classmethod
    def from_dump(cls, dump, cfg=None, log=print):
        state = cls(dump['topology'], dump['plane'], cfg=cfg, log=log)
        for entry in dump['routed']:
            route_id = int(entry['route_id'])
            primitives = entry['primitives']
            prepared = prepare(primitives)
            state.accepted[route_id] = RouteResult(
                route_id, entry.get('family'), entry.get('params') or {}, primitives,
                prepared, prepared.length, 0, 0, prepared.bend_count)
            state.index.add(route_id, prepared)
            state.oracles.add(route_id, prepared)
        for key, failure in (dump.get('failed') or {}).items():
            state.failed[int(key)] = dict(failure)
        return state

    def save_checkpoint(self, path, tag='best'):
        """Geometry-level checkpoint: primitives + statuses, reloadable."""
        data = dict(schema='four_side_1024_v2opt_checkpoint_v1',
                    plane=self.plane, topology=self.topology, tag=tag,
                    timestamp=iso_now(),
                    routed=[dict(route_id=route_id, primitives=result.primitives,
                                 family=result.family, params=result.params)
                            for route_id, result in sorted(self.accepted.items())],
                    failed={str(route_id): failure for route_id, failure
                            in self.failed.items()})
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + '.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        tmp.replace(path)
        return path


def primitives_crossings(record):
    candidate = record.get('candidate') or {}
    crossings = record.get('crossings')
    if crossings is not None:
        return int(crossings)
    return 0


def load_layout_from_checkpoint(topology, plane, checkpoint_path, cfg=None, log=print):
    """Rebuild a LayoutState from a v2opt checkpoint (real primitives)."""
    state = LayoutState(topology, plane, cfg=cfg, log=log)
    data = json.loads(Path(checkpoint_path).read_text(encoding='utf-8'))
    for entry in data['routed']:
        route_id = int(entry['route_id'])
        primitives = entry['primitives']
        prepared = prepare(primitives)
        frame = state.frames[route_id]
        result = RouteResult(route_id, entry.get('family'), entry.get('params') or {},
                             primitives, prepared, prepared.length, 0, 0,
                             prepared.bend_count)
        state.accepted[route_id] = result
        state.index.add(route_id, prepared)
        state.oracles.add(route_id, prepared)
    for key, failure in (data.get('failed') or {}).items():
        state.failed[int(key)] = dict(failure)
    state.source = dict(checkpoint=str(checkpoint_path), tag=data.get('tag'),
                        timestamp=data.get('timestamp'))
    log(f'{plane}: restored checkpoint {Path(checkpoint_path).name} '
        f'({len(state.accepted)} routed)')
    return state


def best_checkpoint_path(out_root, plane):
    return Path(out_root) / 'checkpoints' / f'best_{plane}.json'


def combined_strict_audit(combined_dir):
    """Recompute the combined same-plane conflict count from routes_1024.json."""
    path = Path(combined_dir) / 'routes_1024.json'
    payload = json.loads(path.read_text(encoding='utf-8'))
    plane_records = {'z1': [], 'z2': []}
    for record in payload['routes']:
        if record.get('status') == 'routed':
            plane_records[record['plane']].append(record)
    results = {}
    for plane, records in plane_records.items():
        index = new_index(router_cfg())
        for record in records:
            index.add(record['route_id'], prepare(record['primitives']))
        violations = 0
        for record in records:
            evaluation = index.evaluate(index.routes[record['route_id']],
                                        exclude=[record['route_id']])
            if not evaluation.valid:
                violations += 1
        results[plane] = dict(routed=len(records), violations=violations)
    results['routed'] = sum(item['routed'] for item in results.values())
    results['violations'] = sum(item['violations'] for item in results.values())
    return results
