"""Stage 1: corrected L1 model baseline from the accepted R15 2D layouts.

Both accepted 2D planes are re-interpreted physically correctly:

* every route of plane ``z1`` is a flat L1 route at its true port height z = 0.0 mm;
* every route of plane ``z2`` is a flat L1 route at its true port height z = 0.5 mm;
* both row sets are placed into ONE true-XYZ world.  They belong to the same
  logical interface layer L1 but live on two different physical z planes, so
  cross-row XY crossings are real 3D-separated (0.5 mm) and are not conflicts.

The baseline does not lift anything and does not inherit any old 2.5D result.
Its routed count is the same 2D count (A 943 / B 515) but it is now a physically
valid single-layer-L1 3D baseline and the starting layout for stages 2-4.
"""
from __future__ import annotations

import time
from collections import Counter

from . import common
from .common import PLANES
from .world import World


def build_baseline(scheme, layer_stack, log=print):
    started = time.perf_counter()
    world = World(layer_stack)
    records = []
    routed_by_plane = Counter()
    failed_by_plane = Counter()
    csv_sha = None
    planes = {}
    for plane in PLANES:
        data = common.load_r15_plane(scheme, plane)
        if csv_sha is None:
            csv_sha = data['csv_sha256']
        elif csv_sha != data['csv_sha256']:
            raise ValueError('the two R15 planes disagree on the CSV hash')
        frame_map = data['frames']
        routed = data['routed']
        for route_id in sorted(routed):
            record = common.build_flat_record(route_id, plane, routed[route_id],
                                              frame_map[route_id])
            world.add_route(record)
            records.append(record)
            routed_by_plane[plane] += 1
        for route_id, failed in sorted(data['failed'].items()):
            records.append(common.failed_record(
                route_id, plane, frame_map[route_id],
                failed.get('reason') or 'no_legal_candidate',
                baseline_2d=False, stage='baseline'))
            failed_by_plane[plane] += 1
        planes[plane] = dict(routed=len(routed), failed=len(data['failed']),
                             source=str(data['path']))
    routed_total = sum(routed_by_plane.values())
    failed_total = sum(failed_by_plane.values())
    statistics = dict(
        baseline_routed=int(routed_total), failed=int(failed_total),
        total=int(routed_total + failed_total),
        per_plane={plane: dict(routed=int(routed_by_plane[plane]),
                               failed=int(failed_by_plane[plane]),
                               baseline=int(routed_by_plane[plane]))
                   for plane in PLANES},
        transitions=0, lifted=0,
        physical_planes={str(0.0): 'L1 z1 row',
                         str(0.5): 'L1 z2 row'},
        note=('corrected L1 interface-layer baseline: both port rows belong to L1, '
              'physical heights 0.0 / 0.5 mm; no transition and no old 2.5D result '
              'is inherited'),
        seconds=round(time.perf_counter() - started, 2))
    payload = dict(
        schema='four_side_1024_v2_l3d_routes_v1',
        experiment=(f'V2 corrected L1-L5 physical model, stage 1 baseline, '
                    f'scheme {scheme}'),
        topology='V2', csv_sha256=csv_sha, scheme=scheme,
        scheme_label=common.SCHEME_LABEL[scheme],
        xy_model=common.SCHEME_XY_MODEL[scheme],
        stage='baseline_l1',
        layer_stack=layer_stack.to_dict(),
        process=common.process_record(),
        route_count=len(records),
        routed=int(routed_total), failed=int(failed_total),
        statistics=statistics,
        planes=planes,
        routes=records)
    log(f'[{scheme}] corrected L1 baseline: routed={routed_total} '
        f'(z1={routed_by_plane["z1"]} z2={routed_by_plane["z2"]}), '
        f'failed={failed_total}, world={world.stats()}, '
        f'{statistics["seconds"]}s')
    return payload
