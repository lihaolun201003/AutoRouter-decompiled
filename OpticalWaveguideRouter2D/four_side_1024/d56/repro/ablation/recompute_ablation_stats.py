"""Recompute exact crossing statistics for every ablation checkpoint.

The engine's placement-time crossing counter is order-dependent (a route is
counted when it is placed, so later routes are not included); the delivered
statistics must use the independent exact recomputation.  This script patches
``outputs/four_side_1024_d56_optimized/ablations.json``.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = str(ROOT / '.venv' / 'Scripts' / 'python.exe')
ABL = ROOT / 'outputs/four_side_1024_d56_optimized/ablations.json'

CHECKPOINTS = {
    'A_legacy_order': ROOT / 'scratch/v2A/routes_checkpoint_A_legacy_fixed_order.json',
    'B_opposite_first': ROOT / 'scratch/v2B/routes_checkpoint_B_opposite_first.json',
    'C_opposite_first_dynamic_adjacent':
        ROOT / 'scratch/v2C/routes_checkpoint_C_opposite_first_dynamic_adjacent.json',
    'D_global_congestion': ROOT / 'scratch/v2D/routes_checkpoint_D_global_congestion.json',
    'E_adjacent_first': ROOT / 'scratch/v2E/routes_checkpoint_E_adjacent_first.json',
    'E_best_order': ROOT / 'scratch/v4e/routes_checkpoint_v4e.json',
    'E_best_order_ripup': ROOT / 'scratch/v6rip/routes_checkpoint_v6rip.json',
    'E_best_order_historical_window': ROOT / 'scratch/v5strict/routes_checkpoint_strict.json',
}


def audit(checkpoint):
    out = ROOT / 'scratch' / ('audit_' + checkpoint.stem + '.json')
    subprocess.run([PY, '-m', 'four_side_1024.d56.validate_d56',
                    '--routes', str(checkpoint), '--output', str(out),
                    '--policy', 'exact'], cwd=str(ROOT), check=False,
                   capture_output=True)
    return json.loads(out.read_text(encoding='utf-8'))


def main():
    payload = json.loads(ABL.read_text(encoding='utf-8'))
    rows = payload['experiments']
    by_label = {row['label']: row for row in rows}
    # Legacy_80 has no by_relation field in the historical statistics file
    legacy = by_label.get('Legacy_80')
    if legacy is not None and not legacy.get('by_relation'):
        pair = legacy['by_pair']
        legacy['by_relation'] = {
            'opposite': dict(success=pair['NS']['success'] + pair['EW']['success'],
                             failed=pair['NS']['failed'] + pair['EW']['failed']),
            'adjacent': dict(success=pair['EN']['success'] + pair['ES']['success'] +
                             pair['SW']['success'] + pair['NW']['success'],
                             failed=pair['EN']['failed'] + pair['ES']['failed'] +
                             pair['SW']['failed'] + pair['NW']['failed'])}
        legacy['crossing_policy'] = 'legacy (historical)'
        legacy['geometry'] = 'D56, reverse-engineered AutoRouter first-free adapter'
    general = by_label.get('General_526')
    if general is not None:
        general['crossing_policy'] = 'legacy (historical)'
    for label, checkpoint in CHECKPOINTS.items():
        row = by_label.get(label)
        if row is None or not checkpoint.exists():
            continue
        try:
            data = audit(checkpoint)
        except Exception as exc:  # noqa: BLE001 - diagnostic script
            print(f'{label}: audit failed: {exc}')
            continue
        row['crossing_count'] = data['crossing_count']
        row['crossing_angle_histogram'] = data['crossing_angle_histogram']
        row['crossing_angle_histogram_unit'] = 'degrees, bins as labelled'
        row['small_angle_crossing_count'] = data['small_angle_crossing_count']
        row['spacing_violation_pairs'] = data['spacing_violation_pairs']
        row['overlap_pairs'] = data['overlap_pairs']
        row['touch_pairs'] = data.get('touch_pairs')
        row['crossing_window_overlap_pairs'] = data.get('crossing_window_overlap_pairs')
        row['min_non_crossing_centerline_mm'] = data['min_non_crossing_centerline_mm']
        row['radius_violations'] = data['radius_violations']
        row['boundary_violations'] = data['boundary_violations']
        row['diagonal_line_violations'] = data.get('diagonal_line_violations')
        row['free_or_short_s_arc_violations'] = data.get('free_or_short_s_arc_violations')
        row['independent_audit'] = dict(passed=data['passed'],
                                        policy=data['policy'],
                                        violations=data['violations'])
        print(f"{label:>38s} success={row['success']:>4} "
              f"x={data['crossing_count']:>6} "
              f"small={data['small_angle_crossing_count']:>5} "
              f"spacing={data['spacing_violation_pairs']:>5} "
              f"passed={data['passed']}")
    payload['crossing_count_note'] = (
        'crossing counts are recomputed by the independent validator from the '
        'exact route geometry (not the engine placement-order counter)')
    ABL.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding='utf-8')
    print('patched', ABL)


if __name__ == '__main__':
    main()
