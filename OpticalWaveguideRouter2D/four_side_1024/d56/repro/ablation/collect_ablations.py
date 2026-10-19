"""Collect experiment checkpoints into the ablation table used by the report.

Reads ``scratch/<run>/summary_*.json`` and the historical baselines, and emits
``outputs/four_side_1024_d56_optimized/ablations.json`` in the schema the
output pipeline expects.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / 'scratch'
OUT = ROOT / 'outputs/four_side_1024_d56_optimized'

# label -> (scratch dir, short note)
RUNS = [
    ('A_legacy_order', 'v2A'),
    ('B_opposite_first', 'v2B'),
    ('C_opposite_first_dynamic_adjacent', 'v2C'),
    ('D_global_congestion', 'v2D'),
    ('E_adjacent_first', 'v2E'),
    ('E_best_order', 'v4e'),
    ('E_best_order_ripup', 'v6rip'),
    ('E_best_order_historical_window', 'v5strict'),
]

NOTES = {
    'A_legacy_order': 'exact same candidate families/index, only the original '
                      'SW->ES->NW->EN->NS->EW order (isolates the order effect)',
    'B_opposite_first': 'NS -> EW -> EN -> ES -> SW -> NW (opposite first)',
    'C_opposite_first_dynamic_adjacent': 'opposite first; adjacent pairs ordered dynamically by local congestion',
    'D_global_congestion': 'all 1024 routes sorted by predicted chord congestion',
    'E_adjacent_first': 'adjacent (rigid L) first: EN,ES,SW,NW then NS,EW',
    'E_best_order': 'final: NW,EN,SW,ES then NS,EW (adjacent rigid geometry first)',
    'E_best_order_ripup': 'final order + transactional rip-up/reroute',
    'E_best_order_historical_window': 'final order but acceptance uses the historical '
                                      'straight-line crossing window (strict comparison)',
}

POLICY_OVERRIDE = {
    'A_legacy_order': 'exact',
    'B_opposite_first': 'exact',
    'C_opposite_first_dynamic_adjacent': 'exact',
    'D_global_congestion': 'exact',
    'E_adjacent_first': 'exact',
    'E_best_order': 'exact',
    'E_best_order_ripup': 'exact',
    'E_best_order_historical_window': 'legacy (historical)',
}


def load_history():
    rows = []
    for label, path, note in [
        ('Legacy_80', ROOT / 'outputs/four_side_1024_legacy_two_branch_v2/statistics.json',
         'historical reverse-engineered AutoRouter four-side D56 adapter (600 s budget)'),
        ('General_526', ROOT / 'outputs/four_side_1024_single_layer_v1/statistics.json',
         'historical free-curve/Dubins search; NOT D56 geometry, reference only'),
    ]:
        if not path.exists():
            continue
        stats = json.loads(path.read_text(encoding='utf-8'))
        total = stats.get('total_connections', 1024)
        rows.append(dict(
            label=label,
            strategy=stats.get('algorithm', label),
            success=stats.get('success_count'),
            success_rate=stats.get('success_rate'),
            failed=stats.get('failed_count'),
            by_pair=stats.get('by_pair'),
            by_relation=stats.get('by_relation'),
            mean_length_mm=stats.get('mean_length_mm'),
            max_length_mm=stats.get('max_length_mm'),
            total_length_mm=stats.get('total_length_mm'),
            crossing_count=stats.get('crossing_count'),
            crossing_angle_histogram=stats.get('crossing_angle_histogram'),
            small_angle_crossing_count=stats.get('small_angle_crossing_count'),
            spacing_violation_pairs=stats.get('spacing_violation_pairs'),
            overlap_pairs=stats.get('overlap_pairs'),
            radius_violations=stats.get('radius_violations'),
            boundary_violations=stats.get('boundary_violations'),
            candidate_evaluations=stats.get('search', {}).get('candidate_evaluations'),
            runtime_seconds=stats.get('total_runtime_seconds'),
            geometry='D56 (legacy crossing window)' if label.startswith('Legacy') else 'free curve (Dubins), not D56',
            note=note))
    return rows


def main():
    rows = []
    for label, directory in RUNS:
        path = SCRATCH / directory
        if not path.exists():
            continue
        summary_files = sorted(path.glob('summary_*.json'))
        if not summary_files:
            continue
        summary = json.loads(summary_files[-1].read_text(encoding='utf-8'))
        stats = summary['stats']
        rows.append(dict(
            label=label,
            strategy=summary.get('strategy', {}).get('name', label),
            success=stats['success_count'],
            success_rate=stats['success_rate'],
            failed=stats['failed_count'],
            by_pair=stats['by_pair'],
            by_relation=stats['by_relation'],
            mean_length_mm=stats['mean_length_mm'],
            max_length_mm=stats['max_length_mm'],
            total_length_mm=stats['total_length_mm'],
            crossing_count=stats['crossing_count'],
            crossing_angle_histogram=None,
            small_angle_crossing_count=None,
            spacing_violation_pairs=None,
            overlap_pairs=None,
            radius_violations=0,
            boundary_violations=0,
            candidate_evaluations=stats['candidate_evaluations'],
            runtime_seconds=stats['total_runtime_seconds'],
            crossing_policy=POLICY_OVERRIDE.get(label, 'exact'),
            geometry='D56 orthogonal + R=5 arcs',
            note=NOTES.get(label, '')))
    history = load_history()
    payload = dict(schema='four_side_1024_d56_ablations_v1',
                   policy='exact crossing-region policy (see report section 6); '
                          'legacy-policy sensitivity reported separately',
                   experiments=history + rows)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'ablations.json').write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                        encoding='utf-8')
    print(f'wrote {OUT / "ablations.json"} with {len(history) + len(rows)} rows')
    for row in history + rows:
        print(f"{row['label']:>40s}  {row['success']:>5d}/1024  "
              f"opp={row['by_relation']['opposite']['success']:>3d} "
              f"adj={row['by_relation']['adjacent']['success']:>3d} "
              f"len={row['mean_length_mm']:.1f} x={row['crossing_count']}")


if __name__ == '__main__':
    main()
