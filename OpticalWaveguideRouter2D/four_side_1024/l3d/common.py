"""Shared I/O, port metadata and JSON record helpers for the corrected L1–L5 round."""
from __future__ import annotations

import json
import math
from pathlib import Path

from ..d56.frames import build_frames
from ..fslw import config as C
from ..fslw import ports

PROJECT_ROOT = Path(__file__).resolve().parents[2]
R15_ROOT = PROJECT_ROOT / 'outputs' / 'four_side_1024_v2_r15_v01'
L3D_ROOT = PROJECT_ROOT / 'outputs' / 'four_side_1024_v2_l1l5_v01'
PLANES = ('z1', 'z2')
SCHEME_ALGORITHM = {'A': 'A', 'B': 'B'}
SCHEME_XY_MODEL = {'A': 'd56', 'B': 'ortho90'}
SCHEME_LABEL = {'A': 'A_shortS', 'B': 'B_ortho90'}
ROW_OF_PLANE = {'z1': 1, 'z2': 2}


def plane_dir(scheme, plane):
    return R15_ROOT / 'planes' / 'V2' / scheme / plane


def load_r15_plane(scheme, plane):
    """Load one accepted R15 2D plane and its frames/oracle-state inputs."""
    from ..v2opt.core import LayoutState
    path = plane_dir(scheme, plane) / 'routes.json'
    payload = json.loads(path.read_text(encoding='utf-8'))
    routes, endpoints, _connectors, _validation = ports.load_plane('V2', plane)
    frames = build_frames(routes, endpoints)
    routed, failed = {}, {}
    for record in payload['routes']:
        route_id = int(record['route_id'])
        if record.get('status') == 'routed':
            routed[route_id] = [dict(primitive) for primitive in record['primitives']]
        else:
            failed[route_id] = record
    state = LayoutState.from_history('V2', plane, path, log=lambda *_a, **_k: None)
    return dict(scheme=scheme, plane=plane, path=str(path), payload=payload,
                routes=routes, endpoints=endpoints, frames=frames, routed=routed,
                failed=failed, state=state, csv_sha256=payload.get('csv_sha256'))


def port_xy(frame):
    return ((float(frame.src_xy[0]), float(frame.src_xy[1])),
            (float(frame.dst_xy[0]), float(frame.dst_xy[1])))


def port_meta(plane, frame):
    row = ROW_OF_PLANE[plane]
    z = 0.0 if row == 1 else 0.5
    start, end = port_xy(frame)
    return dict(
        source_row=row, target_row=row,
        source_port=dict(xy=[round(start[0], 9), round(start[1], 9)],
                         z_mm=z, layer_id=1),
        target_port=dict(xy=[round(end[0], 9), round(end[1], 9)],
                         z_mm=z, layer_id=1),
        start_dir=[float(frame.src_inward[0]), float(frame.src_inward[1])],
        end_dir=[-float(frame.dst_inward[0]), -float(frame.dst_inward[1])],
    )


def build_flat_record(route_id, plane, primitives, frame):
    from .world import World
    z = 0.0 if ROW_OF_PLANE[plane] == 1 else 0.5
    route = World.flat_route(route_id, plane, primitives, z)
    route.update(port_meta(plane, frame))
    route['status'] = 'routed'
    route['baseline_2d'] = True
    route['mode'] = 'flat_l1'
    return route


def route_to_record(route, frame):
    """Convert an internal route dict to the schema record."""
    meta = port_meta(route['plane'], frame)
    parts = []
    for part in route['parts']:
        if part['kind'] == 'flat':
            parts.append(dict(
                kind='flat', layer_id=int(part['layer_id']),
                z_mm=round(float(part['z_mm']), 9),
                length_mm=round(float(part['length_mm']), 6),
                primitives=[_clean_primitive(primitive)
                            for primitive in part['primitives']]))
        else:
            parts.append(dict(
                kind='transition',
                from_layer=int(part['from_layer']),
                to_layer=int(part['to_layer']),
                z0=round(float(part['z0']), 9),
                z1=round(float(part['z1']), 9),
                dz_mm=round(float(part['dz_mm']), 9),
                radius_mm=round(float(part['radius_mm']), 9),
                theta_rad=float(part['theta_rad']),
                footprint_mm=round(float(part['footprint_mm']), 9),
                start=[round(float(value), 9) for value in part['start']],
                direction=[round(float(value), 9) for value in part['direction']],
                end=[round(float(value), 9) for value in part['end']],
                length_mm=round(float(part['length_mm']), 6)))
    record = dict(
        route_id=int(route['route_id']),
        plane=route['plane'],
        source_row=int(meta['source_row']),
        target_row=int(meta['target_row']),
        source_port=dict(meta['source_port']),
        target_port=dict(meta['target_port']),
        start_z_mm=round(float(route['start_z_mm']), 9),
        end_z_mm=round(float(route['end_z_mm']), 9),
        layer_sequence=[int(value) for value in route['layer_sequence']],
        layer_z_sequence=[round(float(value), 9) for value in route['layer_z_sequence']],
        n_transitions=int(route['n_transitions']),
        lifted=bool(route['lifted']),
        layers_used=sorted({int(value) for value in route['layer_sequence']}),
        xy_length_mm=round(float(route['xy_length_mm']), 6),
        length_mm=round(float(route['length_mm']), 6),
        z_span_mm=round(float(route['z_span_mm']), 6),
        status='routed',
        baseline_2d=bool(route.get('baseline_2d', False)),
        mode=route.get('mode', 'flat_l1'),
        family=route.get('family'),
        params=route.get('params') or {},
        parts=parts)
    return record


def failed_record(route_id, plane, frame, reason, baseline_2d=False,
                  stage='baseline'):
    return dict(route_id=int(route_id), plane=plane, status='failed',
                reason=reason, baseline_2d=bool(baseline_2d), stage=stage,
                source_row=ROW_OF_PLANE[plane], target_row=ROW_OF_PLANE[plane],
                source_port=dict(port_meta(plane, frame)['source_port']),
                target_port=dict(port_meta(plane, frame)['target_port']))


def process_record():
    return dict(board_mm=[C.BOARD_MM, C.BOARD_MM],
                width_mm=C.WIDTH_MM, edge_gap_mm=C.EDGE_GAP_MM,
                clearance_mm=C.CLEARANCE_MM, radius_mm=C.RADIUS_MM,
                min_cross_angle_deg=C.MIN_CROSS_ANGLE_DEG,
                crossing_policy='strict',
                propagation_loss_db_per_cm=C.PROPAGATION_LOSS_DB_PER_CM,
                bend_loss=dict(status='unknown_uncalibrated'),
                crossing_loss=dict(status='unknown_uncalibrated'),
                interlayer_loss=dict(status='unknown_uncalibrated'),
                loss_note=('no total-loss conclusion is produced: bend, crossing and '
                           'interlayer coefficients are uncalibrated; the 0.05 dB/cm '
                           'propagation value is an experiment convention, not measured'))


def write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + '\n',
                    encoding='utf-8')
    return path


def _clean_primitive(primitive):
    kind = primitive['kind']
    if kind == 'line':
        return dict(kind='line',
                    p0=[round(float(value), 9) for value in primitive['p0']],
                    p1=[round(float(value), 9) for value in primitive['p1']])
    if kind == 'arc':
        return dict(kind='arc',
                    p0=[round(float(value), 9) for value in primitive['p0']],
                    p1=[round(float(value), 9) for value in primitive['p1']],
                    center=[round(float(value), 9) for value in primitive['center']],
                    radius=round(float(primitive['radius']), 9),
                    start_angle=float(primitive['start_angle']),
                    sweep=float(primitive['sweep']))
    raise ValueError(f'unsupported primitive kind {kind!r}')
