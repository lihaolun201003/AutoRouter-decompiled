"""Top-level comparison table: structured A/B vs old Spatial-U and V2 baseline."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAMPAIGN = ROOT / 'outputs/manual_c4_new_connectivity'
OUT_ROOT = CAMPAIGN / 'structured_layer_routing'
import sys
sys.path.insert(0, str(ROOT))
from four_side_1024.v3c4.profile import apply
apply()
from four_side_1024.manual_c4 import structured_layer_routing as S


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _summary(group):
    return _read(OUT_ROOT / group / 'summary.json')


def _old_spatial():
    summary = _read(CAMPAIGN / 'spatial_u_bundle_optimization/summary.json')
    return dict(
        name='旧 Spatial U-bundle (61491c8)', routed=summary.get('routed'),
        unique_crossing_pairs=summary.get('unique_crossing_pairs'),
        transitions=summary.get('transitions'),
        total_length_mm=summary.get('total_length_mm'),
        min_3d_clearance_mm=summary.get('min_3d_clearance_mm'),
        validation_status=summary.get('validation_status'),
        layer_counts={k: v['count'] for k, v in summary['layer_counts'].items()},
        u_target_groups=summary.get('target_quartets_reached'),
        opposite_l2_groups=None,
        adjacent_interface=None,
    )


def _v2(campaign):
    payload = _read(CAMPAIGN / 'phase5_dynamic_optimization/after/routes_l3d.json')
    metrics = S.payload_metrics(campaign, payload, None)
    return dict(
        name='前置 V2 动态优化 (phase5)', routed=metrics['routed'],
        unique_crossing_pairs=metrics['unique_crossing_pairs'],
        transitions=metrics['transitions'],
        total_length_mm=metrics['total_length_mm'],
        min_3d_clearance_mm=0.083207287,
        validation_status='exploratory_only',
        layer_counts={k: v['count'] for k, v in metrics['layer_counts'].items()},
        u_target_groups=None, opposite_l2_groups=None,
        adjacent_interface=None)


def _group_entry(group):
    summary = _summary(group)
    return dict(
        name=f'结构化分层 {group}', routed=summary['routed'],
        unique_crossing_pairs=summary['unique_crossing_pairs'],
        transitions=summary['transitions'],
        total_length_mm=summary['total_length_mm'],
        min_3d_clearance_mm=summary['min_3d_clearance_mm'],
        validation_status=summary.get('validation_status'),
        layer_counts={k: v['count'] for k, v in summary['layer_counts'].items()},
        adjacent_interface=summary.get('adjacent_on_interface'),
        opposite_l2_groups=summary.get('opposite_l2_groups'),
        opposite_l2_routes=summary.get('opposite_l2_routes'),
        opposite_exception_groups=summary.get('opposite_exception_groups'),
        opposite_exception_routes=summary.get('opposite_exception_routes'),
        u_target_groups=summary.get('u_target_reached_groups'),
        u_failed_groups=summary.get('u_failed_groups'),
        crossing_pairs_by_height=summary.get('crossing_pairs_by_height'),
        routes_by_height=summary.get('routes_by_height'),
    )


def main():
    campaign = S.StructuredCampaign(swap_rows=False)
    entries = []
    for group in ('A', 'B'):
        if (OUT_ROOT / group / 'summary.json').exists():
            entries.append(_group_entry(group))
    entries.append(_old_spatial())
    entries.append(_v2(campaign))
    rows = []
    field_map = [
        ('总布通数', 'routed'),
        ('邻边保持接口层', 'adjacent_interface'),
        ('对边集中 L2 组数', 'opposite_l2_groups'),
        ('对边集中 L2 条数', 'opposite_l2_routes'),
        ('对边例外组数', 'opposite_exception_groups'),
        ('对边例外界数', 'opposite_exception_routes'),
        ('U 目标分层组数', 'u_target_groups'),
        ('U 失败组数', 'u_failed_groups'),
        ('全局唯一交叉对', 'unique_crossing_pairs'),
        ('升降次数', 'transitions'),
        ('三维总长 (mm)', 'total_length_mm'),
        ('最小三维净空 (mm)', 'min_3d_clearance_mm'),
        ('独立几何验收', 'validation_status'),
    ]
    for label, key in field_map:
        rows.append(dict(metric=label,
                         values={entry['name']: entry.get(key)
                                 for entry in entries}))
    layer_names = ['L1-z1', 'L1-z2', 'L2', 'L3', 'L4', 'L5']
    for layer in layer_names:
        rows.append(dict(metric=f'{layer} 波导数量',
                         values={entry['name']: (entry['layer_counts'] or {}).get(layer)
                                 for entry in entries}))
    table = dict(
        schema='manual_c4_structured_layer_routing_comparison_v1',
        columns=[entry['name'] for entry in entries],
        rows=rows,
        notes=[
            'A/B 均基于 Manual-C4 2D 底图；旧 Spatial-U 基于 phase5 V2 结果；'
            '前置 V2 作为参考基线单列。',
            '结构化方案把对边连接集中到 L2 后，NS 与 EW 直通线在 z=1.0 形成'
            '大量 90° 交叉，唯一交叉对对 A=19584、B 见上表，高于旧 Spatial-U '
            '的 12824；这是“规则分层优先”的固有代价（任务目标顺序：布通/合法 > '
            '规则分层 > 减少异常抬升 > 交叉与总长）。',
            'A 的对边例外 14 组/56 条（占 1024 的 5.5%），全部保留接口层平铺并在 '
            'opposite_assignment.json 逐组记录原因；B 的例外数见上表。',
            '层高为探索性参数，3D 验收为 exploratory PASS（formal_acceptance=false），'
            '不代表制造工艺正式验收。'])
    (OUT_ROOT / 'comparison_table.json').write_text(
        json.dumps(table, ensure_ascii=False, indent=1), encoding='utf-8')
    lines = ['# 结构化分层布线 A/B 对照表', '',
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
    lines.append('')
    (OUT_ROOT / 'comparison_table.md').write_text('\n'.join(lines) + '\n',
                                                  encoding='utf-8')
    print('comparison written:', len(entries), 'columns,', len(rows), 'rows')


if __name__ == '__main__':
    main()
