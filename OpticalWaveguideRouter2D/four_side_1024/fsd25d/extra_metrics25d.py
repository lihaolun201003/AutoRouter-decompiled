"""Extra crossing metrics for the 2.5D runs.

For each run and plane, the final routes are flattened back to the interface
height and the geometric crossing count of that hypothetical 2D layout is
counted with the frozen fslw pair kernel (crossings are counted for every
broad-phase candidate pair, independent of strict validity).  Comparing it with
the real 3D same-layer crossing count (from validate25d) quantifies how many
crossings the local lifting removed.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(r'C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter2D')
sys.path.insert(0, str(ROOT))

from four_side_1024.fslw import validate_fslw as V
from four_side_1024.fslw import config as C

OUT = ROOT / 'outputs/four_side_1024_v2_25d_v01'
PLANES = ('z1', 'z2')


def route_xy_primitives(record):
    prims = []
    for part in record['parts']:
        if part['kind'] == 'flat':
            for primitive in part['primitives']:
                prims.append(dict(primitive))
        else:
            prims.append(dict(kind='line', p0=list(part['start']),
                              p1=list(part['end'])))
    return prims


def crossing_count(prepared):
    pairs = V._candidate_pairs(prepared, C.CLEARANCE_MM + 2.0 * C.SAGITTA_MM)
    total = 0
    for index_a, index_b in pairs:
        result = V.evaluate_pair(prepared[index_a], prepared[index_b],
                                 C.CLEARANCE_MM, C.SAGITTA_MM, 'strict')
        if result is None:
            continue
        total += len(result['crossings'])
    return total


def plane_crossings(records):
    prepared = []
    for record in records:
        prims = route_xy_primitives(record)
        if not prims:
            continue
        prepared.append(V.prepare_route(prims, route_id=record['route_id']))
    return crossing_count(prepared)


def main():
    summary = {}
    for scheme in ('A', 'B'):
        for layers in (3, 5):
            run_dir = OUT / f'scheme{scheme}' / f'layers{layers}'
            routes_path = run_dir / 'routes_25d.json'
            if not routes_path.exists():
                continue
            payload = json.loads(routes_path.read_text(encoding='utf-8'))
            routed = [record for record in payload['routes']
                      if record['status'] == 'routed']
            per_plane = {}
            for plane in PLANES:
                plane_records = [record for record in routed
                                 if record['plane'] == plane]
                per_plane[plane] = dict(routed=len(plane_records),
                                        flattened_crossings=plane_crossings(plane_records))
            validation_path = OUT / 'validation' / scheme / f'layers{layers}.json'
            actual = None
            by_layer = None
            if validation_path.exists():
                report = json.loads(validation_path.read_text(encoding='utf-8'))
                actual = report.get('crossings', {}).get('total')
                by_layer = report.get('crossings', {}).get('by_layer')
            summary[f'{scheme}{layers}'] = dict(
                scheme=scheme, n_layers=layers, routed=len(routed),
                per_plane=per_plane,
                flattened_total=sum(item['flattened_crossings']
                                    for item in per_plane.values()),
                actual_3d_crossings=actual, by_layer=by_layer,
                crossings_avoided=(sum(item['flattened_crossings']
                                       for item in per_plane.values()) - actual
                                   if actual is not None else None))
            print(f"{scheme}{layers}: routed={len(routed)} "
                  f"flattened={summary[f'{scheme}{layers}']['flattened_total']} "
                  f"actual3d={actual} avoided={summary[f'{scheme}{layers}']['crossings_avoided']} "
                  f"by_layer={by_layer}", flush=True)
    out_path = OUT / 'summary' / 'crossing_metrics.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=1, ensure_ascii=False),
                        encoding='utf-8')
    print('written', out_path)


if __name__ == '__main__':
    main()
