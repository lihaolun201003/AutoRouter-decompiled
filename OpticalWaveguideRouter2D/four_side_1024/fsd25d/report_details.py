"""Collect final run details for the report tables."""
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(r'C:/Users/lihao/Desktop/Graduation Project/OpticalWaveguideRouter2D')
OUT = ROOT / 'outputs/four_side_1024_v2_25d_v01'

result = {}
for scheme in ('A', 'B'):
    for layers in (3, 5):
        run_dir = OUT / f'scheme{scheme}' / f'layers{layers}'
        payload = json.loads((run_dir / 'routes_25d.json').read_text(encoding='utf-8'))
        routed = [r for r in payload['routes'] if r['status'] == 'routed']
        failed = [r for r in payload['routes'] if r['status'] != 'routed']
        stats = payload['statistics']
        lines = arcs = non90 = diag = 0
        for record in routed:
            for part in record['parts']:
                if part['kind'] != 'flat':
                    continue
                for prim in part['primitives']:
                    if prim['kind'] == 'line':
                        lines += 1
                        if abs(prim['p0'][0] - prim['p1'][0]) > 1e-6 and \
                                abs(prim['p0'][1] - prim['p1'][1]) > 1e-6:
                            diag += 1
                    elif prim['kind'] == 'arc':
                        arcs += 1
                        if abs(math.degrees(abs(prim['sweep'])) - 90) > 1e-6:
                            non90 += 1
        per_plane = {}
        for plane in ('z1', 'z2'):
            plane_routes = [r for r in routed if r['plane'] == plane]
            per_plane[plane] = dict(
                routed=len(plane_routes),
                baseline=sum(1 for r in plane_routes if r['baseline_2d']),
                lifted=sum(1 for r in plane_routes if r['lifted']),
                mean_length=round(sum(r['length_mm'] for r in plane_routes)
                                  / len(plane_routes), 2))
        entry = dict(
            routed=len(routed), failed=len(failed),
            new=stats['new_routed'], lifted=stats['lifted'],
            transitions=stats['transitions'],
            total_length=round(stats['total_length_mm'], 2),
            mean_length=round(stats['mean_length_mm'], 2),
            total_xy_length=round(stats['total_xy_length_mm'], 2),
            per_plane=per_plane,
            per_layer_flat_parts=stats['per_layer_flat_parts'],
            failure_reasons=dict(Counter(r['reason'] for r in failed)),
            pairs=dict(Counter(r['pair'] for r in routed)),
            lines=lines, arcs=arcs, non90_arcs=non90, diagonal_lines=diag,
            travel_layers=dict(Counter(str(r['travel_layer']) for r in routed
                                       if r['lifted'])))
        result[f'{scheme}{layers}'] = entry
        print(json.dumps({f'{scheme}{layers}': entry}, ensure_ascii=False, indent=1))

(OUT / 'summary' / 'run_details.json').write_text(
    json.dumps(result, indent=1, ensure_ascii=False), encoding='utf-8')
print('written', OUT / 'summary' / 'run_details.json')
