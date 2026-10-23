"""Runner: hybrid C2/C4 directional layer routing (variant H or V).

Usage:
    python -m four_side_1024.manual_c4.run_hybrid_c2_c4 --variant H
    python -m four_side_1024.manual_c4.run_hybrid_c2_c4 --variant V
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = ROOT / 'outputs/manual_c4_new_connectivity'
A_DIR = CAMPAIGN / 'structured_layer_routing/A'
OUT_ROOT = CAMPAIGN / 'hybrid_c2_c4_directional'
WORK = OUT_ROOT / '_work'

from ..v3c4.profile import apply as _apply_profile
from . import hybrid_c2_c4 as HC
from . import structured_layer_routing as S


def _logger(path):
    def log(message):
        line = time.strftime('%H:%M:%S') + ' ' + str(message)
        print(line, flush=True)
        with path.open('a', encoding='utf-8') as handle:
            handle.write(line + '\n')
    return log


def baseline_stats(data):
    """Directional crossing decomposition of the Structured-A payload."""
    from ..fslw import validate_fslw as V
    records = {int(r['route_id']): r for r in data.a_payload['routes']}
    audit, unique = HC.audit_height(list(records.values()), data.manifest, data)
    z1_opp = set(data.z1_opposite)
    hv = Counter()
    hv_total = 0
    for height, info in audit.items():
        for key, value in info['breakdown'].items():
            parts = key.split(' x ')
            if all(part.startswith('opposite_z1') for part in parts):
                dirs = {part.rsplit('_', 1)[1] for part in parts}
                if dirs == {'EW', 'NS'}:
                    hv[height] += value
                    hv_total += value
    return dict(
        source='structured_layer_routing/A/routes_1024.json',
        unique_crossing_pairs=unique,
        crossing_pairs_by_height={h: info['pairs'] for h, info in audit.items()},
        crossing_breakdown_by_height={h: info['breakdown']
                                      for h, info in audit.items()},
        z1_hv_same_height_pairs=hv_total,
        z1_hv_breakdown_by_height=dict(hv),
        z0_total_pairs=audit.get('0.0', {}).get('pairs'),
        l2_total_pairs=audit.get('1.0', {}).get('pairs'))


def main(argv=None):
    _apply_profile()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant', required=True, choices=['H', 'V'])
    args = parser.parse_args(argv)
    variant = args.variant
    result_dir = OUT_ROOT / variant
    result_dir.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    log = _logger(result_dir / 'run.log')
    started = time.perf_counter()
    data = HC.HybridData()
    log(f'[{variant}] loaded: z1_opposite={len(data.z1_opposite)} '
        f'pairs={len(data.pairs)} fixed_routes={len(data.fixed_routes)}')
    feasibility = json.loads((WORK / f'{variant}_feasibility.json').read_text(
        encoding='utf-8'))
    baseline = baseline_stats(data)
    (WORK / 'A_directional_baseline.json').write_text(
        json.dumps(baseline, ensure_ascii=False, indent=1), encoding='utf-8')

    assembly = HC.assemble_variant(data, feasibility, variant, log=log)
    (WORK / f'{variant}_world.json').write_text(
        json.dumps(dict(schema='hybrid_world_v1', variant=variant,
                        routes=[assembly['world'].plan[rid]
                                for rid in sorted(assembly['world'].plan)]),
                   ensure_ascii=False), encoding='utf-8')
    payload = HC.build_payload(data, variant, assembly, log=log)
    (result_dir / 'routes_1024.json').write_text(
        json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    report = HC.validate(data, payload, log=log)
    runtime = time.perf_counter() - started
    metrics = HC.metrics(data, variant, payload, report, assembly, runtime, log=log)
    # directional layer assignment document
    pair_rows = []
    for pair in data.pairs:
        gid = pair['group_id']
        info = assembly['params'].get(gid)
        lift_rids = pair['ew'] if variant == 'H' else pair['ns']
        row = dict(
            group_id=gid,
            direction='EW' if variant == 'H' else 'NS',
            target_layer=2, target_z_mm=1.0,
            route_ids=lift_rids,
            c2_partner={int(rid): int(pair['ew' if variant == 'H' else 'ns'][1 - i])
                        for i, rid in enumerate(lift_rids)},
            status='lifted_L2' if info else 'kept_L1_z1',
            a_in=info['a_in'] if info else None,
            a_out=info['a_out'] if info else None,
            failure=None if info else assembly['failures'].get(gid),
        )
        if info:
            route = assembly['lifts'].get(int(lift_rids[0]))
            if route:
                parts = route.get('parts') or []
                flats = [p for p in parts if p['kind'] == 'flat']
                transitions = [p for p in parts if p['kind'] == 'transition']
                row['rise_start_xy'] = [round(float(v), 6)
                                        for v in transitions[0]['start']]
                row['fall_start_xy'] = [round(float(v), 6)
                                        for v in transitions[-1]['start']]
                row['rise_start_mm'] = round(float(flats[0]['length_mm']), 6)
                row['fall_start_mm'] = round(
                    float(sum(p['length_mm'] for p in parts[:3])), 6)
        pair_rows.append(row)
    assignment = dict(
        schema='hybrid_c2_c4_pair_assignment_v1', variant=variant,
        total_pairs=len(pair_rows),
        lifted_pairs=sum(1 for row in pair_rows if row['status'] == 'lifted_L2'),
        failed_pairs=sum(1 for row in pair_rows
                         if row['status'] != 'lifted_L2'),
        direction='EW' if variant == 'H' else 'NS',
        kept_direction='NS' if variant == 'H' else 'EW',
        pairs=pair_rows)
    (result_dir / 'c2_pair_assignment.json').write_text(
        json.dumps(assignment, ensure_ascii=False, indent=1), encoding='utf-8')
    (result_dir / 'validation.json').write_text(
        json.dumps(dict(payload_validation=report), ensure_ascii=False, indent=1),
        encoding='utf-8')
    # crossing reduction analysis
    analysis = dict(
        variant=variant,
        baseline=baseline,
        result=dict(
            unique_crossing_pairs=metrics['unique_crossing_pairs'],
            crossing_pairs_by_height=metrics['crossing_pairs_by_height'],
            crossing_breakdown_by_height=metrics['crossing_breakdown_by_height'],
            z1_hv_same_height_pairs=metrics['z1_hv_same_height_pairs'],
            z1_hv_breakdown_by_height=metrics['z1_hv_breakdown_by_height'],
            z0_total_pairs=metrics['crossing_pairs_by_height'].get('0.0'),
            l2_total_pairs=metrics['crossing_pairs_by_height'].get('1.0'),
        ),
        reduction=dict(
            z1_hv_same_height_reduction=(baseline['z1_hv_same_height_pairs']
                                         - metrics['z1_hv_same_height_pairs']),
            z0_total_reduction=(baseline['z0_total_pairs']
                                - (metrics['crossing_pairs_by_height'].get('0.0') or 0)),
            global_reduction=(baseline['unique_crossing_pairs']
                              - metrics['unique_crossing_pairs']),
        ))
    (result_dir / 'crossing_analysis.json').write_text(
        json.dumps(analysis, ensure_ascii=False, indent=1), encoding='utf-8')
    summary = dict(metrics,
                   experiment=f'MANUAL_C4_HYBRID_C2_C4_DIRECTIONAL_{variant}',
                   baseline=baseline['source'],
                   z1_hv_reduction=analysis['reduction'],
                   crossing_analysis='crossing_analysis.json',
                   pair_assignment='c2_pair_assignment.json')
    (result_dir / 'summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
    log(f'[{variant}] validation counts: {report.get("counts")}')
    log(f'[{variant}] DONE runtime={runtime:.1f}s')
    (result_dir / 'READY').write_text('ready\n', encoding='utf-8')
    print(json.dumps({k: summary[k] for k in
                      ('variant', 'routed', 'c2_pairs_lifted', 'c2_pairs_failed',
                       'unique_crossing_pairs', 'z1_hv_same_height_pairs',
                       'transitions', 'min_3d_clearance_mm')},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
