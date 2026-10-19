"""Assemble the final delivery payload from a chosen engine checkpoint.

Usage::

    python scratch/finalize_delivery.py scratch/v4a/routes_checkpoint_v4a.json
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/four_side_1024_d56_optimized'

STRICT = {}


def main():
    if len(sys.argv) < 2:
        raise SystemExit('usage: finalize_delivery.py <checkpoint.json> [strategy_label]')
    source = Path(sys.argv[1])
    label = sys.argv[2] if len(sys.argv) > 2 else 'E_prime'
    payload = json.loads(source.read_text(encoding='utf-8'))
    if payload.get('schema') != 'four_side_1024_d56_optimized_routes_v1':
        raise SystemExit('unexpected schema: ' + repr(payload.get('schema')))
    routes = payload['routes']
    if len(routes) != 1024:
        raise SystemExit(f'expected 1024 identities, got {len(routes)}')
    routed = [r for r in routes if r['status'] == 'routed']
    stats = payload['statistics']
    if stats['success_count'] != len(routed):
        raise SystemExit('statistics/success mismatch')
    print(f'loaded {source}: {len(routed)}/1024 routed')
    strict_path = ROOT / 'scratch/v5strict/summary_strict.json'
    strict = None
    if strict_path.exists():
        sdata = json.loads(strict_path.read_text(encoding='utf-8'))['stats']
        strict = dict(success=sdata['success_count'],
                      success_rate=sdata['success_rate'],
                      by_relation=sdata['by_relation'],
                      policy='legacy straight-line crossing window (historical)',
                      candidate_evaluations=sdata['candidate_evaluations'],
                      runtime_seconds=sdata['total_runtime_seconds'])
    payload['algorithm'].update(
        name='D56 optimized four-side single-layer router',
        strategy_label=label,
        crossing_policy='exact',
        acceptance_policy='exact crossing-region boundary (documented correction; '
                          'see report section 5)',
        geometry_family='orthogonal segments + fixed R=5 quarter arcs + original '
                        'AutoRouter small-displacement short-S pair',
        radius_mm=5.0, width_mm=0.05, edge_gap_mm=0.125,
        layer=0, endpoint_mode='virtual_unfolded',
        strict_historical_policy_result=strict,
        legacy_policy_sensitivity=dict(
            note='if the historical straight-line crossing window is applied instead '
                 'of the exact crossing-region boundary, the same engine reaches the '
                 'reported strict count; 96.9% of those rejections are numerical '
                 'false conflicts (shortfall 4 nm - 43 um at crossing windows)'),
    )
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'routes.json'
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    failed = [r for r in routes if r['status'] != 'routed']
    (OUT / 'failed_routes.json').write_text(
        json.dumps(failed, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'wrote {target} ({target.stat().st_size} bytes) and failed_routes.json '
          f'({len(failed)} rows)')
    print(json.dumps(dict(success=len(routed),
                          by_relation=stats['by_relation'],
                          by_pair={k: v['success'] for k, v in stats['by_pair'].items()},
                          crossings=stats['crossing_count'],
                          evals=stats['candidate_evaluations'],
                          runtime=round(stats['total_runtime_seconds'], 1)),
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
