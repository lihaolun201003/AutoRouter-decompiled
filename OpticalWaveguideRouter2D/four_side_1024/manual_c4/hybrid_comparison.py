"""Comparison table for the hybrid C2/C4 directional routing experiment."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = ROOT / 'outputs/manual_c4_new_connectivity'
OUT_ROOT = CAMPAIGN / 'hybrid_c2_c4_directional'
A_SUMMARY = CAMPAIGN / 'structured_layer_routing/A/summary.json'
SPATIAL_SUMMARY = CAMPAIGN / 'spatial_u_bundle_optimization/summary.json'


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main():
    entries = []
    for variant in ('H', 'V'):
        summary = _read(OUT_ROOT / variant / 'summary.json')
        entries.append(dict(
            name=f'Hybrid {variant}',
            routed=summary.get('routed'),
            c2_pairs_lifted=summary.get('c2_pairs_lifted'),
            c2_pairs_total=summary.get('c2_pairs_total'),
            z1_hv_same_height_pairs=summary.get('z1_hv_same_height_pairs'),
            z0_pairs=summary.get('crossing_pairs_by_height', {}).get('0.0'),
            l2_pairs=summary.get('crossing_pairs_by_height', {}).get('1.0'),
            unique_crossing_pairs=summary.get('unique_crossing_pairs'),
            transitions=summary.get('transitions'),
            total_length_mm=summary.get('total_length_mm'),
            min_3d_clearance_mm=summary.get('min_3d_clearance_mm'),
            validation_status=summary.get('validation_status'),
            validation_counts=summary.get('validation_counts'),
            layer_counts={k: v['count']
                          for k, v in summary.get('layer_counts', {}).items()},
            direction=summary.get('lifted_direction')))
    a = _read(A_SUMMARY)
    baseline_path = OUT_ROOT / '_work' / 'A_directional_baseline.json'
    baseline_audit = _read(baseline_path) if baseline_path.exists() else None
    a_cross = ((baseline_audit or {}).get('crossing_pairs_by_height')
               or a.get('crossing_pairs_by_height', {}))
    a_hv = ((baseline_audit or {}).get('z1_hv_same_height_pairs'))
    entries.append(dict(
        name='旧 Structured A', routed=a.get('routed'),
        c2_pairs_lifted=None, c2_pairs_total=None,
        z1_hv_same_height_pairs=a_hv,
        z0_pairs=a_cross.get('0.0'), l2_pairs=a_cross.get('1.0'),
        unique_crossing_pairs=a.get('unique_crossing_pairs'),
        transitions=a.get('transitions'),
        total_length_mm=a.get('total_length_mm'),
        min_3d_clearance_mm=a.get('min_3d_clearance_mm'),
        validation_status=a.get('validation_status'),
        layer_counts={k: v['count'] for k, v in a.get('layer_counts', {}).items()},
        direction='横向/纵向均混合于 L2/L1'))
    sp = _read(SPATIAL_SUMMARY)
    entries.append(dict(
        name='旧 Spatial U-bundle', routed=sp.get('routed'),
        c2_pairs_lifted=None, c2_pairs_total=None,
        z1_hv_same_height_pairs=None,
        z0_pairs=sp.get('crossing_pairs_by_height', {}).get('0.0'),
        l2_pairs=sp.get('crossing_pairs_by_height', {}).get('1.0'),
        unique_crossing_pairs=sp.get('unique_crossing_pairs'),
        transitions=sp.get('transitions'),
        total_length_mm=sp.get('total_length_mm'),
        min_3d_clearance_mm=sp.get('min_3d_clearance_mm'),
        validation_status=sp.get('validation_status'),
        layer_counts={k: v['count'] for k, v in sp.get('layer_counts', {}).items()},
        direction='随机逐四元组抬升'))
    fields = [
        ('总布通数', 'routed'),
        ('C2 二元组抬升数', 'c2_pairs_lifted'),
        ('z1 横纵同层交叉对', 'z1_hv_same_height_pairs'),
        ('z=0 交叉对', 'z0_pairs'),
        ('L2 交叉对', 'l2_pairs'),
        ('全局唯一交叉对', 'unique_crossing_pairs'),
        ('升降次数', 'transitions'),
        ('三维总长 (mm)', 'total_length_mm'),
        ('最小三维净空 (mm)', 'min_3d_clearance_mm'),
        ('独立 3D 验收', 'validation_status'),
    ]
    rows = [dict(metric=label,
                 values={entry['name']: entry.get(key) for entry in entries})
            for label, key in fields]
    for layer in ('L1-z1', 'L1-z2', 'L2', 'L3', 'L4', 'L5'):
        rows.append(dict(metric=f'{layer} 波导数量',
                         values={entry['name']:
                                 (entry['layer_counts'] or {}).get(layer)
                                 for entry in entries}))
    # reductions vs Structured A
    baseline = next(entry for entry in entries if entry['name'] == '旧 Structured A')
    baseline_hv = baseline.get('z1_hv_same_height_pairs')
    reductions = {}
    for entry in entries[:2]:
        reductions[entry['name']] = dict(
            z0_reduction=(baseline['z0_pairs'] - entry['z0_pairs'])
            if baseline['z0_pairs'] is not None and entry['z0_pairs'] is not None else None,
            global_reduction=(baseline['unique_crossing_pairs']
                              - entry['unique_crossing_pairs'])
            if baseline['unique_crossing_pairs'] is not None else None,
            z1_hv_reduction=None)
        if entry['z1_hv_same_height_pairs'] is not None and baseline_hv is not None:
            reductions[entry['name']]['z1_hv_reduction'] = (
                baseline_hv - entry['z1_hv_same_height_pairs'])
    table = dict(
        schema='hybrid_c2_c4_comparison_v1',
        columns=[entry['name'] for entry in entries],
        rows=rows,
        reductions_vs_A=reductions,
        notes=[
            'H：z1 横向 E↔W 全部优先升 L2，纵向 N↔S 留在 L1-z1；V 为反向对照。'
            'z1 只要求 C2（180°旋转），z2 保持严格 C4 且 U 线束固定为 Structured-A。',
            'A 的 z1 横纵同层交叉对 = 10928（z=0 为 9928、L2 为 1000，'
            '由结构化分层交叉分解得到；A 官方 summary 的 z=0 计数为 18600，'
            '本表统一用独立 fslw 审计的唯一交叉对口径 17576）；H/V 把两个方向放到不同物理高度后，'
            '剩余的 7032 对全部来自"抬升方向的 z=0 base 直线段"与"保留方向"'
            '的同层交叉（深升降窗口导致），并非目标层平面交叉。',
            'z=0 总交叉对从 17576 降到 11952（减少 5624）；全局唯一交叉对从 '
            '19584 降到 12960（减少 6624）。',
            '深升降窗口的结构性原因：z2 接口层相邻路线在 z=0.5 与 z1 横向 line '
            '同排并行（parallel shadow），R15 + dz=1.0 的 S 升降足印 7.68mm，'
            '无法在影子段之前完成上升；34 个 C2 二元组只能选择深窗口。'
            '这是本轮主要瓶颈（详见 shadow_bottleneck_analysis.json）。',
            '层高为探索性参数，3D 验收为 exploratory PASS（formal_acceptance=false）。'])
    (OUT_ROOT / 'comparison_table.json').write_text(
        json.dumps(table, ensure_ascii=False, indent=1), encoding='utf-8')
    lines = ['# Hybrid C2/C4 方向分层对照表', '',
             '| 指标 | ' + ' | '.join(table['columns']) + ' |',
             '|---|' + '|'.join(['---:'] * len(table['columns'])) + '|']
    for row in rows:
        values = []
        for column in table['columns']:
            value = row['values'].get(column)
            if isinstance(value, float):
                values.append(f'{value:,.3f}')
            elif value is None:
                values.append('—')
            else:
                values.append(str(value))
        lines.append(f"| {row['metric']} | " + ' | '.join(values) + ' |')
    lines.append('')
    for note in table['notes']:
        lines.append(f'> {note}')
    (OUT_ROOT / 'comparison_table.md').write_text('\n'.join(lines) + '\n',
                                                  encoding='utf-8')
    print('comparison written:', [entry['name'] for entry in entries])


if __name__ == '__main__':
    main()
